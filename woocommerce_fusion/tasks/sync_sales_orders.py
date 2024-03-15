import json
from datetime import datetime
from random import randrange
from typing import Dict, List, Optional
from urllib.parse import urlparse

import frappe
from frappe import _, _dict
from frappe.utils import get_datetime, now
from frappe.utils.data import cstr

from woocommerce_fusion.tasks.sync import SynchroniseWooCommerce
from woocommerce_fusion.woocommerce.doctype.woocommerce_integration_settings.woocommerce_integration_settings import (
	WooCommerceIntegrationSettings,
)
from woocommerce_fusion.woocommerce.doctype.woocommerce_order.woocommerce_order import (
	WC_ORDER_STATUS_MAPPING,
	WC_ORDER_STATUS_MAPPING_REVERSE,
)
from woocommerce_fusion.woocommerce.woocommerce_api import (
	generate_woocommerce_record_name_from_domain_and_id,
)


@frappe.whitelist()
def run_sales_orders_sync_in_background():
	# Publish update to websocket if called from UI
	# frappe.publish_realtime(
	# 	"wc_sync_items",
	# 	message={"description": "Sending Background Job to Queue", "count": 0, "total": 0},
	# 	doctype="Item",
	# )

	frappe.enqueue(run_sales_orders_sync, queue="long")


def run_sales_orders_sync_from_hook(doc, method):
	if doc == "Sales Order":
		frappe.enqueue(run_sales_orders_sync, queue="long", sales_order_name=doc.name)


@frappe.whitelist()
def run_sales_orders_sync(
	sales_order_name: Optional[str] = None, woocommerce_order_id: Optional[str] = None
):
	sync = SynchroniseSalesOrders(
		sales_order_name=sales_order_name, woocommerce_order_id=woocommerce_order_id
	)
	sync.run()


class SynchroniseSalesOrders(SynchroniseWooCommerce):
	"""
	Class for managing synchronisation of WooCommerce Orders with ERPNext Sales Orders
	"""

	wc_orders_dict: Dict
	sales_orders_list: List
	sales_order_name: Optional[str]
	woocommerce_order_id: Optional[str]
	date_time_from: str | datetime
	date_time_to: str | datetime

	def __init__(
		self,
		settings: Optional[WooCommerceIntegrationSettings | _dict] = None,
		sales_order_name: Optional[str] = None,
		woocommerce_order_id: Optional[str] = None,
		date_time_from: Optional[str | datetime] = None,
		date_time_to: Optional[str | datetime] = None,
	) -> None:
		super().__init__(settings)
		self.wc_orders_dict = {}
		self.sales_orders_list = []
		self.sales_order_name = sales_order_name
		self.date_time_from = date_time_from
		self.date_time_to = date_time_to
		self.woocommerce_order_id = woocommerce_order_id

		self.set_date_range()

	def set_date_range(self):
		"""
		Validate date_time_from and date_time_to
		"""
		# If no 'Sales Order List' or 'To Date' were supplied, default to synchronise all orders
		# since last synchronisation
		if not self.sales_order_name and not self.date_time_to:
			self.date_time_from = self.settings.wc_last_sync_date

	def run(self):
		"""
		Run synchronisation
		"""
		self.get_woocommerce_orders_modified_since()
		self.get_erpnext_sales_orders_for_wc_orders()
		self.get_erpnext_sales_orders_modified_since()
		self.get_woocommerce_orders_for_erpnext_sales_orders()
		self.sync_wc_orders_with_erpnext_sales_orders()

	def get_woocommerce_orders_modified_since(self):
		"""
		Get list of WooCommerce orders modified since date_time_from
		"""
		# If this is a sync run for all Sales Orders, get list of WooCommerce orders
		if not self.sales_order_name:
			# Get active WooCommerce orders
			self.get_list_of_wc_orders(date_time_from=self.date_time_from)

			# Get trashed WooCommerce orders
			self.get_list_of_wc_orders(date_time_from=self.date_time_from, status="trash")

	def get_erpnext_sales_orders_for_wc_orders(self):
		"""
		Get list of erpnext orders linked to woocommerce orders
		"""
		if self.sales_order_name:
			self.get_erpnext_sales_orders(sales_order_name=self.sales_order_name)
		else:
			self.get_erpnext_sales_orders(woocommerce_orders=self.wc_orders_dict)

	def get_erpnext_sales_orders_modified_since(self):
		"""
		Get list of erpnext orders modified since date_time_from
		"""
		if not self.sales_order_name:
			self.get_erpnext_sales_orders(date_time_from=self.date_time_from)

	def get_erpnext_sales_orders(
		self,
		date_time_from: datetime = None,
		woocommerce_orders: Dict = None,
		sales_order_name: str = None,
	):
		"""
		Get list of erpnext orders

		At lease one of date_time_from, woocommerce_orders or sales_order_name is required
		"""
		if not any([date_time_from, woocommerce_orders, sales_order_name]):
			return

		filters = [
			["Sales Order", "woocommerce_id", "is", "set"],
			["Sales Order", "woocommerce_server", "is", "set"],
		]
		if self.settings.minimum_creation_date:
			filters.append(["Sales Order", "modified", ">", self.settings.minimum_creation_date])
		if date_time_from:
			filters.append(["Sales Order", "modified", ">", self.date_time_from])
		if woocommerce_orders:
			filters.append(
				["Sales Order", "woocommerce_id", "in", [order["id"] for order in woocommerce_orders.values()]]
			)
			filters.append(
				[
					"Sales Order",
					"woocommerce_server",
					"in",
					[order["woocommerce_server"] for order in woocommerce_orders.values()],
				]
			)
		if sales_order_name:
			filters.append(["Sales Order", "name", "=", sales_order_name])

		self.sales_orders_list.extend(
			frappe.get_all(
				"Sales Order",
				filters=filters,
				fields=[
					"name",
					"woocommerce_id",
					"woocommerce_server",
					"modified",
					"docstatus",
					"woocommerce_payment_entry",
					"custom_attempted_woocommerce_auto_payment_entry",
				],
			)
		)

	def get_woocommerce_orders_for_erpnext_sales_orders(self):
		"""
		Get more WooCommerce orders linked to our Sales Order(s)
		"""
		self.get_list_of_wc_orders(
			sales_orders=self.sales_orders_list, woocommerce_order_id=self.woocommerce_order_id
		),

	def get_list_of_wc_orders(
		self,
		date_time_from: Optional[datetime] = None,
		date_time_to: Optional[datetime] = None,
		sales_orders: Optional[List] = None,
		woocommerce_order_id: Optional[str] = None,
		status: Optional[str] = None,
	):
		"""
		Fetches a list of WooCommerce Orders within a specified date range or linked with Sales Orders, using pagination.

		At least one of date_time_from, date_time_to, or sales_orders parameters are required
		"""
		if not any([date_time_from, date_time_to, sales_orders, woocommerce_order_id]):
			return

		wc_records_per_page_limit = 100
		page_length = wc_records_per_page_limit
		new_results = True
		start = 0
		filters = []
		minimum_creation_date = self.settings.minimum_creation_date

		# Build filters
		if date_time_from:
			filters.append(["WooCommerce Order", "date_modified", ">", date_time_from])
		if date_time_to:
			filters.append(["WooCommerce Order", "date_modified", "<", date_time_to])
		if minimum_creation_date:
			filters.append(["WooCommerce Order", "date_created", ">", minimum_creation_date])
		if sales_orders:
			wc_order_ids = [sales_order.woocommerce_id for sales_order in sales_orders]
			filters.append(["WooCommerce Order", "id", "in", wc_order_ids])
		if woocommerce_order_id:
			filters.append(["WooCommerce Order", "id", "=", woocommerce_order_id])
		if status:
			filters.append(["WooCommerce Order", "status", "=", status])

		while new_results:
			woocommerce_order = frappe.get_doc({"doctype": "WooCommerce Order"})
			new_results = woocommerce_order.get_list(
				args={"filters": filters, "page_lenth": page_length, "start": start}
			)
			for wc_order in new_results:
				self.wc_orders_dict[wc_order["name"]] = wc_order
			start += page_length

	def sync_wc_orders_with_erpnext_sales_orders(self):
		"""
		Syncronise Sales Orders between ERPNext and WooCommerce
		"""
		# Create a dictionary for quick access
		sales_orders_dict = {
			generate_woocommerce_record_name_from_domain_and_id(
				so.woocommerce_server, so.woocommerce_id
			): so
			for so in self.sales_orders_list
		}

		# Loop through each order
		for wc_order in self.wc_orders_dict.values():
			if wc_order["name"] in sales_orders_dict:
				so = sales_orders_dict[wc_order["name"]]
				# If the Sales Order exists and it has been updated after last_updated, update it
				if get_datetime(wc_order["date_modified"]) > get_datetime(so.modified):
					self.update_sales_order(wc_order, so.name)
				if get_datetime(wc_order["date_modified"]) < get_datetime(so.modified) and so.docstatus == 1:
					self.update_woocommerce_order(wc_order, so.name)

				# If the Sales Order exists and has been submitted in the mean time, sync Payment Entries
				if (
					so.docstatus == 1
					and not so.woocommerce_payment_entry
					and not so.custom_attempted_woocommerce_auto_payment_entry
				):
					self.create_and_link_payment_entry(wc_order, so.name)
			else:
				# If the Sales Order does not exist, create it
				self.create_sales_order(wc_order)

		# Update Last Sales Order Sync Date Time
		if not self.sales_order_name or self.woocommerce_order_id:
			self.settings.wc_last_sync_date = now()
			self.settings.save()

	def update_sales_order(self, woocommerce_order, sales_order_name):
		"""
		Update the ERPNext Sales Order with fields from it's corresponding WooCommerce Order
		"""
		# Get the Sales Order doc
		sales_order = frappe.get_doc("Sales Order", sales_order_name)

		# Get the WooCommerce Order doc
		wc_order = frappe.get_doc({"doctype": "WooCommerce Order", "name": woocommerce_order["name"]})
		wc_order.load_from_db()

		# Update the woocommerce_status field if necessary
		wc_order_status = WC_ORDER_STATUS_MAPPING_REVERSE[wc_order.status]
		if sales_order.woocommerce_status != wc_order_status:
			sales_order.woocommerce_status = wc_order_status
			sales_order.save()

		# Update the payment_method_title field if necessary
		if sales_order.woocommerce_payment_method != wc_order.payment_method_title:
			sales_order.woocommerce_payment_method = wc_order.payment_method_title

		if not sales_order.woocommerce_payment_entry:
			self.create_and_link_payment_entry(woocommerce_order, sales_order_name)

	def create_and_link_payment_entry(self, wc_order_data: Dict, sales_order_name: str) -> None:
		"""
		Create a Payment Entry for WooCommerce Orders that have been marked as Paid
		"""
		try:
			sales_order = frappe.get_doc("Sales Order", sales_order_name)
			wc_server = next(
				(
					server
					for server in self.settings.servers
					if sales_order.woocommerce_server in server.woocommerce_server_url
				),
				None,
			)
			if not wc_server:
				raise ValueError("Could not find woocommerce_server in list of servers")

			# Validate that WooCommerce order has been paid, and that sales order doesn't have a linked Payment Entry yet
			if (
				wc_server.enable_payments_sync
				and wc_order_data["payment_method"]
				and wc_order_data["date_paid"]
				and not sales_order.woocommerce_payment_entry
				and sales_order.docstatus == 1
			):
				# Get Company Bank Account for this Payment Method
				payment_method_bank_account_mapping = json.loads(wc_server.payment_method_bank_account_mapping)

				if wc_order_data["payment_method"] not in payment_method_bank_account_mapping:
					raise KeyError(
						f"WooCommerce payment method {wc_order_data['payment_method']} not found in WooCommerce Integration Settings"
					)

				company_bank_account = payment_method_bank_account_mapping[wc_order_data["payment_method"]]

				if company_bank_account:
					# Get G/L Account for this Payment Method
					payment_method_gl_account_mapping = json.loads(wc_server.payment_method_gl_account_mapping)
					company_gl_account = payment_method_gl_account_mapping[wc_order_data["payment_method"]]

					# Create a new Payment Entry
					company = frappe.get_value("Account", company_gl_account, "company")
					meta_data = wc_order_data.get("meta_data", None)

					# Attempt to get Payfast Transaction ID
					payment_reference_no = wc_order_data.get("transaction_id", None)

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
					payment_entry_dict = {
						"company": company,
						"payment_type": "Receive",
						"reference_no": payment_reference_no or wc_order_data["payment_method_title"],
						"reference_date": wc_order_data["date_paid"],
						"party_type": "Customer",
						"party": sales_order.customer,
						"posting_date": wc_order_data["date_paid"],
						"paid_amount": float(wc_order_data["total"]),
						"received_amount": float(wc_order_data["total"]),
						"bank_account": company_bank_account,
						"paid_to": company_gl_account,
					}
					payment_entry = frappe.new_doc("Payment Entry")
					payment_entry.update(payment_entry_dict)
					row = payment_entry.append("references")
					row.reference_doctype = "Sales Order"
					row.reference_name = sales_order.name
					row.total_amount = sales_order.grand_total
					row.allocated_amount = sales_order.grand_total
					payment_entry.save()

					# Link created Payment Entry to Sales Order
					sales_order.woocommerce_payment_entry = payment_entry.name

				sales_order.custom_attempted_woocommerce_auto_payment_entry = 1
				sales_order.save()

		except Exception as e:
			frappe.log_error(
				"WooCommerce Sync Task Error",
				f"Failed to create Payment Entry for WooCommerce Order {wc_order_data['name']}\n{frappe.get_traceback()}",
			)
			return

	@staticmethod
	def update_woocommerce_order(wc_order_data: Dict, sales_order_name: str) -> None:
		"""
		Update the WooCommerce Order with fields from it's corresponding ERPNext Sales Order
		"""
		wc_order_dirty = False

		# Get the Sales Order doc
		sales_order = frappe.get_doc("Sales Order", sales_order_name)

		# Get the WooCommerce Order doc
		wc_order = frappe.get_doc({"doctype": "WooCommerce Order", "name": wc_order_data["name"]})
		wc_order.load_from_db()

		# Update the woocommerce_status field if necessary
		sales_order_wc_status = WC_ORDER_STATUS_MAPPING[sales_order.woocommerce_status]
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
		sales_order_items_changed = False
		line_items = json.loads(wc_order.line_items)
		# Check if count of line items are different
		if len(line_items) != len(sales_order.items):
			sales_order_items_changed = True
		# Check if any line item properties changed
		else:
			for i, so_item in enumerate(sales_order.items):
				if (
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
			try:
				wc_order.save()
			except Exception:
				frappe.log_error(
					"WooCommerce Sync Task Error",
					f"Failed to update WooCommerce Order {wc_order_data['name']}\n{frappe.get_traceback()}",
				)

	def create_sales_order(self, wc_order_data: Dict) -> None:
		"""
		Create an ERPNext Sales Order from the given WooCommerce Order
		"""
		raw_billing_data = wc_order_data.get("billing")
		raw_shipping_data = wc_order_data.get("shipping")
		customer_name = f"{raw_billing_data.get('first_name')} {raw_billing_data.get('last_name')}"
		customer_docname = self.create_or_link_customer_and_address(
			raw_billing_data, raw_shipping_data, customer_name
		)
		try:
			site_domain = urlparse(wc_order_data.get("_links")["self"][0]["href"]).netloc
		except Exception:
			error_message = f"{frappe.get_traceback()}\n\n Order Data: \n{str(wc_order_data.as_dict())}"
			frappe.log_error("WooCommerce Error", error_message)
			raise
		self.create_missing_items(wc_order_data.get("line_items"), site_domain)

		new_sales_order = frappe.new_doc("Sales Order")
		new_sales_order.customer = customer_docname
		new_sales_order.po_no = new_sales_order.woocommerce_id = wc_order_data.get("id")

		try:
			site_domain = urlparse(wc_order_data.get("_links")["self"][0]["href"]).netloc
			new_sales_order.woocommerce_status = WC_ORDER_STATUS_MAPPING_REVERSE[
				wc_order_data.get("status")
			]
		except Exception:
			error_message = f"{frappe.get_traceback()}\n\n Order Data: \n{str(wc_order_data.as_dict())}"
			frappe.log_error("WooCommerce Error", error_message)
			raise

		new_sales_order.woocommerce_server = site_domain
		new_sales_order.woocommerce_payment_method = wc_order_data.get("payment_method_title", None)
		new_sales_order.naming_series = self.settings.sales_order_series or "SO-WOO-"
		created_date = wc_order_data.get("date_created").split("T")
		new_sales_order.transaction_date = created_date[0]
		delivery_after = self.settings.delivery_after_days or 7
		new_sales_order.delivery_date = frappe.utils.add_days(created_date[0], delivery_after)
		new_sales_order.company = self.settings.company
		self.set_items_in_sales_order(new_sales_order, wc_order_data)
		new_sales_order.flags.ignore_mandatory = True
		try:
			new_sales_order.insert()
			if self.settings.submit_sales_orders:
				new_sales_order.submit()
		except Exception:
			error_message = (
				f"{frappe.get_traceback()}\n\nSales Order Data: \n{str(new_sales_order.as_dict())})"
			)
			frappe.log_error("WooCommerce Error", error_message)

		self.create_and_link_payment_entry(wc_order_data, new_sales_order.name)

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

	def create_missing_items(self, items_list, woocommerce_site):
		"""
		Searching for items linked to multiple WooCommerce sites
		"""
		for item_data in items_list:
			item_woo_com_id = cstr(item_data.get("product_id"))

			item_codes = frappe.db.get_all(
				"Item WooCommerce Server",
				filters={"woocommerce_id": item_woo_com_id, "woocommerce_server": woocommerce_site},
				fields=["parent"],
			)
			found_item = frappe.get_doc("Item", item_codes[0].parent) if item_codes else None
			if not found_item:
				# Create Item
				item = frappe.new_doc("Item")
				item.item_code = _("woocommerce - {0}").format(item_woo_com_id)
				item.stock_uom = self.settings.uom or _("Nos")
				item.item_group = self.settings.item_group
				item.item_name = item_data.get("name")
				row = item.append("woocommerce_servers")
				row.woocommerce_id = item_woo_com_id
				row.woocommerce_server = woocommerce_site
				item.flags.ignore_mandatory = True
				item.save()

	def set_items_in_sales_order(self, new_sales_order, order):
		"""
		Customised version of set_items_in_sales_order to allow searching for items linked to
		multiple WooCommerce sites
		"""
		if not self.settings.warehouse:
			frappe.throw(_("Please set Warehouse in WooCommerce Integration Settings"))

		for item in order.get("line_items"):
			woocomm_item_id = item.get("product_id")

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
					"uom": self.settings.uom or _("Nos"),
					"qty": item.get("quantity"),
					"rate": item.get("price")
					if self.settings.use_actual_tax_type
					else get_tax_inc_price_for_woocommerce_line_item(item),
					"warehouse": self.settings.warehouse,
				},
			)

			if not self.settings.use_actual_tax_type:
				new_sales_order.taxes_and_charges = self.settings.sales_taxes_and_charges_template

				# Trigger taxes calculation
				new_sales_order.set_missing_lead_customer_details()
			else:
				ordered_items_tax = item.get("total_tax")
				add_tax_details(
					new_sales_order, ordered_items_tax, "Ordered Item tax", self.settings.tax_account
				)

		add_tax_details(
			new_sales_order, order.get("shipping_tax"), "Shipping Tax", self.settings.f_n_f_account
		)
		add_tax_details(
			new_sales_order,
			order.get("shipping_total"),
			"Shipping Total",
			self.settings.f_n_f_account,
		)


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


# @frappe.whitelist(allow_guest=True)
# def custom_order(*args, **kwargs):
# 	"""
# 	Overrided version of erpnext.erpnext_integrations.connectors.woocommerce_connection.order
# 	in order to populate our custom fields when a Webhook is received
# 	"""
# 	try:
# 		# ==================================== Custom code starts here ==================================== #
# 		# Original code
# 		# _order(*args, **kwargs)
# 		_custom_order(*args, **kwargs)
# 		# ==================================== Custom code starts here ==================================== #
# 	except Exception:
# 		error_message = (
# 			# ==================================== Custom code starts here ==================================== #
# 			# Original Code
# 			# frappe.get_traceback() + "\n\n Request Data: \n" + json.loads(frappe.request.data).__str__()
# 			frappe.get_traceback()
# 			+ "\n\n Request Data: \n"
# 			+ str(frappe.request.data)
# 			# ==================================== Custom code starts here ==================================== #
# 		)
# 		frappe.log_error("WooCommerce Error", error_message)
# 		raise


# def _custom_order(*args, **kwargs):
# 	"""
# 	Overrided version of erpnext.erpnext_integrations.connectors.woocommerce_connection._order
# 	in order to populate our custom fields when a Webhook is received
# 	"""
# 	woocommerce_settings = frappe.get_doc("Woocommerce Settings")
# 	if frappe.flags.woocomm_test_order_data:
# 		order = frappe.flags.woocomm_test_order_data
# 		event = "created"

# 	elif frappe.request and frappe.request.data:
# 		verify_request()
# 		try:
# 			order = json.loads(frappe.request.data)
# 		except ValueError:
# 			# woocommerce returns 'webhook_id=value' for the first request which is not JSON
# 			order = frappe.request.data
# 		event = frappe.get_request_header("X-Wc-Webhook-Event")

# 	else:
# 		return "success"

# 	if event == "created":
# 		sys_lang = frappe.get_single("System Settings").language or "en"
# 		raw_billing_data = order.get("billing")
# 		raw_shipping_data = order.get("shipping")
# 		customer_name = f"{raw_billing_data.get('first_name')} {raw_billing_data.get('last_name')}"
# 		customer_docname = link_customer_and_address(raw_billing_data, raw_shipping_data, customer_name)
# 		# ==================================== Custom code starts here ==================================== #
# 		# Original code
# 		# link_items(order.get("line_items"), woocommerce_settings, sys_lang)
# 		# create_sales_order(order, woocommerce_settings, customer_name, sys_lang)
# 		try:
# 			site_domain = urlparse(order.get("_links")["self"][0]["href"]).netloc
# 		except Exception:
# 			error_message = f"{frappe.get_traceback()}\n\n Order Data: \n{str(order.as_dict())}"
# 			frappe.log_error("WooCommerce Error", error_message)
# 			raise
# 		custom_link_items(
# 			order.get("line_items"), woocommerce_settings, sys_lang, woocommerce_site=site_domain
# 		)
# 		custom_create_sales_order(order, woocommerce_settings, customer_docname, sys_lang)
# 		# ==================================== Custom code ends here ==================================== #
