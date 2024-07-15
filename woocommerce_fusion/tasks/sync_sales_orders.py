import json
from datetime import datetime
from random import randrange
from typing import Dict, Optional

import frappe
from erpnext.selling.doctype.sales_order.sales_order import SalesOrder
from frappe import _
from frappe.utils import get_datetime
from frappe.utils.data import cstr, now

from woocommerce_fusion.exceptions import SyncDisabledError
from woocommerce_fusion.tasks.sync import SynchroniseWooCommerce
from woocommerce_fusion.tasks.sync_items import run_item_sync
from woocommerce_fusion.woocommerce.doctype.woocommerce_order.woocommerce_order import (
	WC_ORDER_STATUS_MAPPING,
	WC_ORDER_STATUS_MAPPING_REVERSE,
	WooCommerceOrder,
)
from woocommerce_fusion.woocommerce.woocommerce_api import (
	generate_woocommerce_record_name_from_domain_and_id,
)


def run_sales_order_sync_from_hook(doc, method):
	if (
		doc.doctype == "Sales Order"
		and not doc.flags.get("created_by_sync", None)
		and doc.woocommerce_server
	):
		frappe.enqueue(run_sales_order_sync, queue="long", sales_order_name=doc.name)


@frappe.whitelist()
def run_sales_order_sync(
	sales_order_name: Optional[str] = None,
	sales_order: Optional[SalesOrder] = None,
	woocommerce_order_name: Optional[str] = None,
	woocommerce_order: Optional[WooCommerceOrder] = None,
	enqueue=False,
):
	"""
	Helper funtion that prepares arguments for order sync
	"""
	# Validate inputs, at least one of the parameters should be provided
	if not any([sales_order_name, sales_order, woocommerce_order_name, woocommerce_order]):
		raise ValueError(
			"At least one of sales_order_name, sales_order, woocommerce_order_name, woocommerce_order is required"
		)

	# Get ERPNext Sales Order and WooCommerce Order if they exist
	if woocommerce_order or woocommerce_order_name:
		if not woocommerce_order:
			woocommerce_order = frappe.get_doc(
				{"doctype": "WooCommerce Order", "name": woocommerce_order_name}
			)
			woocommerce_order.load_from_db()

		# Trigger sync
		sync = SynchroniseSalesOrder(woocommerce_order=woocommerce_order)
		if enqueue:
			frappe.enqueue(sync.run)
		else:
			sync.run()

	elif sales_order_name or sales_order:
		if not sales_order:
			sales_order = frappe.get_doc("Sales Order", sales_order_name)
		if not sales_order.woocommerce_server:
			frappe.throw(_("No WooCommerce Server defined for Sales Order {0}").format(sales_order_name))
		# Trigger sync for every linked server
		sync = SynchroniseSalesOrder(sales_order=sales_order)
		if enqueue:
			frappe.enqueue(sync.run)
		else:
			sync.run()

	return (
		sync.sales_order if sync else None,
		sync.woocommerce_order if sync else None,
	)


def sync_woocommerce_orders_modified_since(date_time_from=None):
	"""
	Get list of WooCommerce orders modified since date_time_from
	"""
	wc_settings = frappe.get_doc("WooCommerce Integration Settings")

	if not date_time_from:
		date_time_from = wc_settings.wc_last_sync_date

	# Validate
	if not date_time_from:
		error_text = _(
			"'Last Items Syncronisation Date' field on 'WooCommerce Integration Settings' is missing"
		)
		frappe.log_error(
			"WooCommerce Items Sync Task Error",
			error_text,
		)
		raise ValueError(error_text)

	wc_orders = get_list_of_wc_orders(date_time_from=date_time_from)
	wc_orders += get_list_of_wc_orders(date_time_from=date_time_from, status="trash")
	for wc_order in wc_orders:
		try:
			run_sales_order_sync(woocommerce_order=wc_order, enqueue=True)
		# Skip orders with errors, as these exceptions will be logged
		except Exception:
			pass

	wc_settings.reload()
	wc_settings.wc_last_sync_date = now()
	wc_settings.flags.ignore_mandatory = True
	wc_settings.save()


class SynchroniseSalesOrder(SynchroniseWooCommerce):
	"""
	Class for managing synchronisation of a WooCommerce Order with an ERPNext Sales Order
	"""

	def __init__(
		self,
		sales_order: Optional[SalesOrder] = None,
		woocommerce_order: Optional[WooCommerceOrder] = None,
	) -> None:
		super().__init__()
		self.sales_order = sales_order
		self.woocommerce_order = woocommerce_order
		self.settings = frappe.get_cached_doc("WooCommerce Integration Settings")

	def run(self):
		"""
		Run synchronisation
		"""
		try:
			self.get_corresponding_sales_order_or_woocommerce_order()
			self.sync_wc_order_with_erpnext_order()
		except Exception as err:
			error_message = f"{frappe.get_traceback()}\n\nSales Order Data: \n{str(self.sales_order.as_dict()) if self.sales_order else ''}\n\nWC Product Data \n{str(self.woocommerce_order.as_dict()) if self.woocommerce_order else ''})"
			frappe.log_error("WooCommerce Error", error_message)
			raise err

	def get_corresponding_sales_order_or_woocommerce_order(self):
		"""
		If we have an ERPNext Sales Order, get the corresponding WooCommerce Order
		If we have a WooCommerce Order, get the corresponding ERPNext Sales Order
		"""
		if self.sales_order and not self.woocommerce_order and self.sales_order.woocommerce_id:
			# Validate that this Sales Order's WooCommerce Server has sync enabled
			wc_server = frappe.get_cached_doc("WooCommerce Server", self.sales_order.woocommerce_server)
			if not wc_server.enable_sync:
				raise SyncDisabledError(wc_server)

			wc_orders = get_list_of_wc_orders(sales_order=self.sales_order)
			self.woocommerce_order = wc_orders[0]

		if self.woocommerce_order and not self.sales_order:
			self.get_erpnext_sales_order()

	def get_erpnext_sales_order(self):
		"""
		Get erpnext item for a WooCommerce Product
		"""
		filters = [
			["Sales Order", "woocommerce_id", "is", "set"],
			["Sales Order", "woocommerce_server", "is", "set"],
		]
		filters.append(["Sales Order", "woocommerce_id", "=", self.woocommerce_order.id])
		filters.append(
			[
				"Sales Order",
				"woocommerce_server",
				"=",
				self.woocommerce_order.woocommerce_server,
			]
		)

		sales_orders = frappe.get_all(
			"Sales Order",
			filters=filters,
			fields=["name"],
		)
		if len(sales_orders) > 0:
			self.sales_order = frappe.get_doc("Sales Order", sales_orders[0].name)

	def sync_wc_order_with_erpnext_order(self):
		"""
		Syncronise Sales Order between ERPNext and WooCommerce
		"""
		if self.sales_order and not self.woocommerce_order:
			# create missing order in WooCommerce
			pass
		elif self.woocommerce_order and not self.sales_order:
			# create missing order in ERPNext
			self.create_sales_order(self.woocommerce_order)
		elif self.sales_order and self.woocommerce_order:
			# both exist, check sync hash
			if (
				self.woocommerce_order.woocommerce_date_modified
				!= self.sales_order.custom_woocommerce_last_sync_hash
			):
				if get_datetime(self.woocommerce_order.woocommerce_date_modified) > get_datetime(
					self.sales_order.modified
				):
					self.update_sales_order(self.woocommerce_order, self.sales_order)
				if get_datetime(self.woocommerce_order.woocommerce_date_modified) < get_datetime(
					self.sales_order.modified
				):
					self.update_woocommerce_order(self.woocommerce_order, self.sales_order)

			# If the Sales Order exists and has been submitted in the mean time, sync Payment Entries
			if (
				self.sales_order.docstatus == 1
				and not self.sales_order.woocommerce_payment_entry
				and not self.sales_order.custom_attempted_woocommerce_auto_payment_entry
			):
				self.sales_order.reload()
				if self.create_and_link_payment_entry(self.woocommerce_order, self.sales_order):
					self.sales_order.save()

	def update_sales_order(self, woocommerce_order: WooCommerceOrder, sales_order: SalesOrder):
		"""
		Update the ERPNext Sales Order with fields from it's corresponding WooCommerce Order
		"""
		# Ignore cancelled Sales Orders
		if sales_order.docstatus != 2:
			so_dirty = False

			# Update the woocommerce_status field if necessary
			wc_order_status = WC_ORDER_STATUS_MAPPING_REVERSE[woocommerce_order.status]
			if sales_order.woocommerce_status != wc_order_status:
				sales_order.woocommerce_status = wc_order_status
				so_dirty = True

			# Update the payment_method_title field if necessary
			if sales_order.woocommerce_payment_method != woocommerce_order.payment_method_title:
				sales_order.woocommerce_payment_method = woocommerce_order.payment_method_title
				so_dirty = True

			if not sales_order.woocommerce_payment_entry:
				if self.create_and_link_payment_entry(woocommerce_order, sales_order):
					so_dirty = True

			if so_dirty:
				sales_order.flags.created_by_sync = True
				sales_order.save()

	def create_and_link_payment_entry(
		self, wc_order: WooCommerceOrder, sales_order: SalesOrder
	) -> bool:
		"""
		Create a Payment Entry for a WooCommerce Order that has been marked as Paid
		"""
		wc_server = frappe.get_cached_doc("WooCommerce Server", sales_order.woocommerce_server)
		if not wc_server:
			raise ValueError("Could not find woocommerce_server in list of servers")

		# Validate that WooCommerce order has been paid, and that sales order doesn't have a linked Payment Entry yet
		if (
			wc_server.enable_payments_sync
			and wc_order.payment_method
			and ((wc_server.ignore_date_paid) or (not wc_server.ignore_date_paid and wc_order.date_paid))
			and not sales_order.woocommerce_payment_entry
			and sales_order.docstatus == 1
		):
			# Get Company Bank Account for this Payment Method
			payment_method_bank_account_mapping = json.loads(wc_server.payment_method_bank_account_mapping)

			if wc_order.payment_method not in payment_method_bank_account_mapping:
				raise KeyError(
					f"WooCommerce payment method {wc_order.payment_method} not found in WooCommerce Server"
				)

			company_bank_account = payment_method_bank_account_mapping[wc_order.payment_method]

			if company_bank_account:
				# Get G/L Account for this Payment Method
				payment_method_gl_account_mapping = json.loads(wc_server.payment_method_gl_account_mapping)
				company_gl_account = payment_method_gl_account_mapping[wc_order.payment_method]

				# Create a new Payment Entry
				company = frappe.get_value("Account", company_gl_account, "company")
				meta_data = wc_order.get("meta_data", None)

				# Attempt to get Payfast Transaction ID
				payment_reference_no = wc_order.get("transaction_id", None)

				# Attempt to get Yoco Transaction ID
				if not payment_reference_no:
					payment_reference_no = (
						next(
							(data["value"] for data in meta_data if data["key"] == "yoco_order_payment_id"),
							None,
						)
						if meta_data and type(meta_data) is list
						else None
					)

				# Determine if the reference should be Sales Order or Sales Invoice
				reference_doctype = "Sales Order"
				reference_name = sales_order.name
				total_amount = sales_order.grand_total
				if sales_order.per_billed > 0:
					si_item_details = frappe.get_all(
						"Sales Invoice Item",
						fields=["name", "parent"],
						filters={"sales_order": sales_order.name},
					)
					if len(si_item_details) > 0:
						reference_doctype = "Sales Invoice"
						reference_name = si_item_details[0].parent
						total_amount = sales_order.grand_total

				# Create Payment Entry
				payment_entry_dict = {
					"company": company,
					"payment_type": "Receive",
					"reference_no": payment_reference_no or wc_order.payment_method_title,
					"reference_date": wc_order.date_paid or sales_order.transaction_date,
					"party_type": "Customer",
					"party": sales_order.customer,
					"posting_date": wc_order.date_paid or sales_order.transaction_date,
					"paid_amount": float(wc_order.total),
					"received_amount": float(wc_order.total),
					"bank_account": company_bank_account,
					"paid_to": company_gl_account,
				}
				payment_entry = frappe.new_doc("Payment Entry")
				payment_entry.update(payment_entry_dict)
				row = payment_entry.append("references")
				row.reference_doctype = reference_doctype
				row.reference_name = reference_name
				row.total_amount = total_amount
				row.allocated_amount = total_amount
				payment_entry.save()

				# Link created Payment Entry to Sales Order
				sales_order.woocommerce_payment_entry = payment_entry.name

			sales_order.custom_attempted_woocommerce_auto_payment_entry = 1
			return True

	@staticmethod
	def update_woocommerce_order(wc_order: WooCommerceOrder, sales_order: SalesOrder) -> None:
		"""
		Update the WooCommerce Order with fields from it's corresponding ERPNext Sales Order
		"""
		wc_order_dirty = False

		# Update the woocommerce_status field if necessary
		sales_order_wc_status = (
			WC_ORDER_STATUS_MAPPING[sales_order.woocommerce_status]
			if sales_order.woocommerce_status
			else None
		)
		if sales_order_wc_status != wc_order.status:
			wc_order.status = sales_order_wc_status
			wc_order_dirty = True

		# Get the Item WooCommerce ID's
		for so_item in sales_order.items:
			so_item.woocommerce_id = frappe.get_value(
				"Item WooCommerce Server",
				filters={"parent": so_item.item_code, "woocommerce_server": wc_order.woocommerce_server},
				fieldname="woocommerce_id",
			)

		# Update the line_items field if necessary
		wc_server = frappe.get_cached_doc("WooCommerce Server", wc_order.woocommerce_server)
		if wc_server.sync_so_items_to_wc:
			sales_order_items_changed = False
			line_items = json.loads(wc_order.line_items)
			# Check if count of line items are different
			if len(line_items) != len(sales_order.items):
				sales_order_items_changed = True
			# Check if any line item properties changed
			else:
				for i, so_item in enumerate(sales_order.items):
					if not so_item.woocommerce_id:
						break
					elif (
						int(so_item.woocommerce_id) != line_items[i]["product_id"]
						or so_item.qty != line_items[i]["quantity"]
						or so_item.rate != get_tax_inc_price_for_woocommerce_line_item(line_items[i])
					):
						sales_order_items_changed = True
						break

			if sales_order_items_changed:
				# Set the product_id for existing lines to null, to clear the line items for the WooCommerce order
				replacement_line_items = [
					{"id": line_item["id"], "product_id": None} for line_item in json.loads(wc_order.line_items)
				]
				# Add the correct lines
				replacement_line_items.extend(
					[
						{"product_id": so_item.woocommerce_id, "quantity": so_item.qty, "price": so_item.rate}
						for so_item in sales_order.items
					]
				)
				wc_order.line_items = json.dumps(replacement_line_items)
				wc_order_dirty = True

		if wc_order_dirty:
			wc_order.save()

	def create_sales_order(self, wc_order: WooCommerceOrder) -> None:
		"""
		Create an ERPNext Sales Order from the given WooCommerce Order
		"""
		raw_billing_data = json.loads(wc_order.billing)
		raw_shipping_data = json.loads(wc_order.shipping)
		customer_name = f"{raw_billing_data.get('first_name')} {raw_billing_data.get('last_name')}"
		customer_docname = self.create_or_link_customer_and_address(
			raw_billing_data, raw_shipping_data, customer_name
		)
		self.create_missing_items(wc_order, json.loads(wc_order.line_items), wc_order.woocommerce_server)

		new_sales_order = frappe.new_doc("Sales Order")
		new_sales_order.customer = customer_docname
		new_sales_order.po_no = new_sales_order.woocommerce_id = wc_order.id

		new_sales_order.woocommerce_status = WC_ORDER_STATUS_MAPPING_REVERSE[wc_order.status]
		wc_server = frappe.get_cached_doc("WooCommerce Server", wc_order.woocommerce_server)

		new_sales_order.woocommerce_server = wc_order.woocommerce_server
		new_sales_order.woocommerce_payment_method = wc_order.payment_method_title
		created_date = wc_order.date_created.split("T")
		new_sales_order.transaction_date = created_date[0]
		delivery_after = wc_server.delivery_after_days or 7
		new_sales_order.delivery_date = frappe.utils.add_days(created_date[0], delivery_after)
		new_sales_order.company = wc_server.company
		new_sales_order.currency = wc_order.currency
		self.set_items_in_sales_order(new_sales_order, wc_order)
		new_sales_order.flags.ignore_mandatory = True
		new_sales_order.flags.created_by_sync = True
		new_sales_order.insert()
		if wc_server.submit_sales_orders:
			new_sales_order.submit()

		new_sales_order.reload()
		self.create_and_link_payment_entry(wc_order, new_sales_order)
		new_sales_order.save()

	@staticmethod
	def create_or_link_customer_and_address(
		raw_billing_data: Dict, raw_shipping_data: Dict, customer_name: str
	) -> None:
		"""
		Create or update Customer and Address records
		"""
		customer_woo_com_email = raw_billing_data.get("email")
		customer_exists = frappe.get_value("Customer", {"woocommerce_email": customer_woo_com_email})
		if not customer_exists:
			# Create Customer
			customer = frappe.new_doc("Customer")
			customer_docname = customer_name[:3].upper() + f"{randrange(1, 10**3):03}"
			customer.name = customer_docname
		else:
			# Edit Customer
			customer = frappe.get_doc("Customer", {"woocommerce_email": customer_woo_com_email})
			old_name = customer.customer_name

		customer.customer_name = customer_name
		customer.woocommerce_email = customer_woo_com_email
		customer.flags.ignore_mandatory = True

		try:
			customer.save()
		except Exception:
			error_message = f"{frappe.get_traceback()}\n\nCustomer Data{str(customer.as_dict())}"
			frappe.log_error("WooCommerce Error", error_message)

		if customer_exists:
			for address_type in (
				"Billing",
				"Shipping",
			):
				try:
					address = frappe.get_doc(
						"Address", {"woocommerce_email": customer_woo_com_email, "address_type": address_type}
					)
					rename_address(address, customer)
				except (
					frappe.DoesNotExistError,
					frappe.DuplicateEntryError,
					frappe.ValidationError,
				):
					pass
		else:
			create_address(raw_billing_data, customer, "Billing")
			create_address(raw_shipping_data, customer, "Shipping")
			create_contact(raw_billing_data, customer)

		return customer.name

	def create_missing_items(self, wc_order, items_list, woocommerce_site):
		"""
		Searching for items linked to multiple WooCommerce sites
		"""
		for item_data in items_list:
			item_woo_com_id = cstr(item_data.get("variation_id") or item_data.get("product_id"))

			# Deleted items will have a "0" for variation_id/product_id
			if item_woo_com_id != "0":
				woocommerce_product_name = generate_woocommerce_record_name_from_domain_and_id(
					woocommerce_site, item_woo_com_id
				)
				run_item_sync(woocommerce_product_name=woocommerce_product_name)

	def set_items_in_sales_order(self, new_sales_order, wc_order):
		"""
		Customised version of set_items_in_sales_order to allow searching for items linked to
		multiple WooCommerce sites
		"""
		wc_server = frappe.get_cached_doc("WooCommerce Server", new_sales_order.woocommerce_server)
		if not wc_server.warehouse:
			frappe.throw(_("Please set Warehouse in WooCommerce Server"))

		for item in json.loads(wc_order.line_items):
			woocomm_item_id = item.get("variation_id") or item.get("product_id")

			# Deleted items will have a "0" for variation_id/product_id
			if woocomm_item_id == 0:
				found_item = create_placeholder_item(new_sales_order)
			else:
				iws = frappe.qb.DocType("Item WooCommerce Server")
				itm = frappe.qb.DocType("Item")
				item_codes = (
					frappe.qb.from_(iws)
					.join(itm)
					.on(iws.parent == itm.name)
					.where(
						(iws.woocommerce_id == cstr(woocomm_item_id))
						& (iws.woocommerce_server == new_sales_order.woocommerce_server)
						& (itm.disabled == 0)
					)
					.select(iws.parent)
					.limit(1)
				).run(as_dict=True)

				found_item = frappe.get_doc("Item", item_codes[0].parent) if item_codes else None

			new_sales_order.append(
				"items",
				{
					"item_code": found_item.name,
					"item_name": found_item.item_name,
					"description": found_item.item_name,
					"delivery_date": new_sales_order.delivery_date,
					"qty": item.get("quantity"),
					"rate": item.get("price")
					if wc_server.use_actual_tax_type
					else get_tax_inc_price_for_woocommerce_line_item(item),
					"warehouse": wc_server.warehouse,
					"discount_percentage": 100 if item.get("price") == 0 else 0,
				},
			)

			if not wc_server.use_actual_tax_type:
				new_sales_order.taxes_and_charges = wc_server.sales_taxes_and_charges_template

				# Trigger taxes calculation
				new_sales_order.set_missing_lead_customer_details()
			else:
				ordered_items_tax = item.get("total_tax")
				add_tax_details(new_sales_order, ordered_items_tax, "Ordered Item tax", wc_server.tax_account)

		add_tax_details(new_sales_order, wc_order.shipping_tax, "Shipping Tax", wc_server.f_n_f_account)
		add_tax_details(
			new_sales_order,
			wc_order.shipping_total,
			"Shipping Total",
			wc_server.f_n_f_account,
		)

		# Handle scenario where Woo Order has no items, then manually set the total
		if len(new_sales_order.items) == 0:
			new_sales_order.base_grand_total = float(wc_order.total)
			new_sales_order.grand_total = float(wc_order.total)
			new_sales_order.base_rounded_total = float(wc_order.total)
			new_sales_order.rounded_total = float(wc_order.total)


def get_list_of_wc_orders(
	date_time_from: Optional[datetime] = None,
	sales_order: Optional[SalesOrder] = None,
	status: Optional[str] = None,
):
	"""
	Fetches a list of WooCommerce Orders within a specified date range or linked with a Sales Order, using pagination.

	At least one of date_time_from, or sales_order parameters are required
	"""
	if not any([date_time_from, sales_order]):
		raise ValueError("At least one of date_time_from or sales_order parameters are required")

	wc_records_per_page_limit = 100
	page_length = wc_records_per_page_limit
	new_results = True
	start = 0
	filters = []
	wc_orders = []

	wc_settings = frappe.get_cached_doc("WooCommerce Integration Settings")
	minimum_creation_date = wc_settings.minimum_creation_date

	# Build filters
	if date_time_from:
		filters.append(["WooCommerce Order", "date_modified", ">", date_time_from])
	if minimum_creation_date:
		filters.append(["WooCommerce Order", "date_created", ">", minimum_creation_date])
	if sales_order:
		filters.append(["WooCommerce Order", "id", "=", sales_order.woocommerce_id])
	if status:
		filters.append(["WooCommerce Order", "status", "=", status])

	while new_results:
		woocommerce_order = frappe.get_doc({"doctype": "WooCommerce Order"})
		new_results = woocommerce_order.get_list(
			args={"filters": filters, "page_lenth": page_length, "start": start, "as_doc": True}
		)
		for wc_order in new_results:
			wc_orders.append(wc_order)
		start += page_length
		if len(new_results) < page_length:
			new_results = []

	return wc_orders


def rename_address(address, customer):
	old_address_title = address.name
	new_address_title = customer.name + "-" + address.address_type
	address.address_title = customer.customer_name
	address.save()

	frappe.rename_doc("Address", old_address_title, new_address_title)


def create_address(raw_data, customer, address_type):
	address = frappe.new_doc("Address")

	address.address_line1 = raw_data.get("address_1", "Not Provided")
	address.address_line2 = raw_data.get("address_2", "Not Provided")
	address.city = raw_data.get("city", "Not Provided")
	address.woocommerce_email = customer.woocommerce_email
	address.address_type = address_type
	address.country = frappe.get_value("Country", {"code": raw_data.get("country", "IN").lower()})
	address.state = raw_data.get("state")
	address.pincode = raw_data.get("postcode")
	address.phone = raw_data.get("phone")
	address.email_id = customer.woocommerce_email
	address.address_title = f"{customer.name}-{address_type}"
	address.append("links", {"link_doctype": "Customer", "link_name": customer.name})

	address.flags.ignore_mandatory = True
	address.save()


def create_contact(data, customer):
	email = data.get("email", None)
	phone = data.get("phone", None)

	if not email and not phone:
		return

	contact = frappe.new_doc("Contact")
	contact.first_name = data.get("first_name")
	contact.last_name = data.get("last_name")
	contact.is_primary_contact = 1
	contact.is_billing_contact = 1

	if phone:
		contact.add_phone(phone, is_primary_mobile_no=1, is_primary_phone=1)

	if email:
		contact.add_email(email, is_primary=1)

	contact.append("links", {"link_doctype": "Customer", "link_name": customer.name})

	contact.flags.ignore_mandatory = True
	contact.save()


def add_tax_details(sales_order, price, desc, tax_account_head):
	sales_order.append(
		"taxes",
		{
			"charge_type": "Actual",
			"account_head": tax_account_head,
			"tax_amount": price,
			"description": desc,
		},
	)


def get_tax_inc_price_for_woocommerce_line_item(line_item: Dict):
	"""
	WooCommerce's Line Item "price" field will always show the tax excluding amount.
	This function calculates the tax inclusive rate for an item
	"""
	return (float(line_item.get("subtotal")) + float(line_item.get("subtotal_tax"))) / float(
		line_item.get("quantity")
	)


def create_placeholder_item(sales_order: SalesOrder):
	"""
	Create a placeholder Item for deleted WooCommerce Products
	"""
	wc_server = frappe.get_cached_doc("WooCommerce Server", sales_order.woocommerce_server)
	if not frappe.db.exists("Item", "DELETED_WOOCOMMERCE_PRODUCT"):
		item = frappe.new_doc("Item")
		item.item_code = "DELETED_WOOCOMMERCE_PRODUCT"
		item.item_name = "Deletet WooCommerce Product"
		item.description = "Deletet WooCommerce Product"
		item.item_group = "All Item Groups"
		item.stock_uom = wc_server.uom
		item.is_stock_item = 0
		item.is_fixed_asset = 0
		item.opening_stock = 0
		item.flags.created_by_sync = True
		item.save()
	else:
		item = frappe.get_doc("Item", "DELETED_WOOCOMMERCE_PRODUCT")
	return item
