import json
from urllib.parse import urlparse

import frappe
from frappe.utils import get_datetime, now

from woocommerce_fusion.overrides.erpnext_integrations.woocommerce_connection import (
	custom_create_sales_order,
	custom_link_items,
	link_customer_and_address,
)
from woocommerce_fusion.woocommerce.doctype.woocommerce_order.woocommerce_order import (
	WC_ORDER_STATUS_MAPPING,
	WC_ORDER_STATUS_MAPPING_REVERSE,
	generate_woocommerce_order_name_from_domain_and_id,
)


@frappe.whitelist()
def sync_sales_orders(
	sales_order_name=None, date_time_from=None, date_time_to=None, update_sync_date_in_settings=True
):
	"""
	Syncronise Sales Orders between ERPNext and WooCommerce
	"""
	# Fetch WooCommerce Settings
	woocommerce_settings = frappe.get_doc("Woocommerce Settings")

	# Fetch WooCommerce Additional Settings
	woocommerce_additional_settings = frappe.get_single("WooCommerce Additional Settings")

	wc_order_list = []

	# If no 'Sales Order List' or 'To Date' were supplied, default to synchronise all orders
	# since last synchronisation
	if not sales_order_name and not date_time_to:
		date_time_from = woocommerce_additional_settings.wc_last_sync_date

	if sales_order_name:
		wc_order_list = get_list_of_wc_orders_from_sales_order(sales_order_name=sales_order_name)
	else:
		wc_order_list = get_list_of_wc_orders(
			date_time_from,
			date_time_to,
			minimum_creation_date=woocommerce_additional_settings.minimum_creation_date,
		)

	# Get list of Sales Orders
	sales_orders = frappe.get_all(
		"Sales Order",
		filters={
			"woocommerce_id": ["in", [order["id"] for order in wc_order_list]],
			"woocommerce_site": ["in", [order["woocommerce_site"] for order in wc_order_list]],
			"docstatus": 1,
		},
		fields=["name", "woocommerce_id", "woocommerce_site", "modified"],
	)

	# Create a dictionary for quick access
	sales_orders_dict = {
		generate_woocommerce_order_name_from_domain_and_id(so.woocommerce_site, so.woocommerce_id): so
		for so in sales_orders
	}

	# Loop through each order
	for order in wc_order_list:
		if order["name"] in sales_orders_dict:
			# If the Sales Order exists and it has been updated after last_updated, update it
			if get_datetime(order["date_modified"]) > get_datetime(
				sales_orders_dict[order["name"]].modified
			):
				update_sales_order(order, sales_orders_dict[order["name"]].name)
			if get_datetime(order["date_modified"]) < get_datetime(
				sales_orders_dict[order["name"]].modified
			):
				update_woocommerce_order(order, sales_orders_dict[order["name"]].name)
		else:
			# If the Sales Order does not exist, create it
			create_sales_order(order, woocommerce_settings, woocommerce_additional_settings)

	# Update Last Sales Order Sync Date Time
	if update_sync_date_in_settings:
		woocommerce_additional_settings.wc_last_sync_date = now()
		woocommerce_additional_settings.save()


def get_list_of_wc_orders_from_sales_order(sales_order_name):
	"""
	Fetches the associated WooCommerce Order for a given Sales Order name and returns it in a list
	"""
	sales_order = frappe.get_doc("Sales Order", sales_order_name)
	wc_order_name = generate_woocommerce_order_name_from_domain_and_id(
		domain=sales_order.woocommerce_site,
		order_id=sales_order.woocommerce_id,
	)
	wc_order = frappe.get_doc({"doctype": "WooCommerce Order", "name": wc_order_name})
	wc_order.load_from_db()
	return [wc_order.__dict__]


def get_list_of_wc_orders(date_time_from=None, date_time_to=None, minimum_creation_date=None):
	"""
	Fetches a list of WooCommerce Orders within a specified date range using pagination
	"""
	wc_order_list = []
	wc_records_per_page_limit = 100
	page_length = wc_records_per_page_limit
	new_results = True
	start = 0
	filters = []
	filters.append(
		["WooCommerce Order", "date_modified", ">", date_time_from]
	) if date_time_from else None
	filters.append(
		["WooCommerce Order", "date_modified", "<", date_time_to]
	) if date_time_to else None
	filters.append(
		["WooCommerce Order", "date_created", ">", minimum_creation_date]
	) if minimum_creation_date else None
	while new_results:
		woocommerce_order = frappe.get_doc({"doctype": "WooCommerce Order"})
		new_results = woocommerce_order.get_list(
			args={"filters": filters, "page_lenth": page_length, "start": start}
		)
		wc_order_list.extend(new_results)
		start += page_length
	return wc_order_list


def update_sales_order(woocommerce_order, sales_order_name):
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
		create_and_link_payment_entry(woocommerce_order, sales_order_name)


def update_woocommerce_order(woocommerce_order, sales_order_name):
	"""
	Update the WooCommerce Order with fields from it's corresponding ERPNext Sales Order
	"""
	# Get the Sales Order doc
	sales_order = frappe.get_doc("Sales Order", sales_order_name)

	# Get the WooCommerce Order doc
	wc_order = frappe.get_doc({"doctype": "WooCommerce Order", "name": woocommerce_order["name"]})
	wc_order.load_from_db()

	# Update the woocommerce_status field if necessary
	sales_order_wc_status = WC_ORDER_STATUS_MAPPING[sales_order.woocommerce_status]
	if sales_order_wc_status != wc_order.status:
		wc_order.status = sales_order_wc_status
		try:
			wc_order.save()
		except Exception:
			frappe.log_error(
				"WooCommerce Sync Task Error",
				f"Failed to update WooCommerce Order {woocommerce_order['name']}\n{frappe.get_traceback()}",
			)


def create_sales_order(order, woocommerce_settings, woocommerce_additional_settings):
	"""
	Create an ERPNext Sales Order from the given WooCommerce Order
	"""
	sys_lang = frappe.get_single("System Settings").language or "en"
	raw_billing_data = order.get("billing")
	raw_shipping_data = order.get("shipping")
	customer_name = f"{raw_billing_data.get('first_name')} {raw_billing_data.get('last_name')}"
	customer_docname = link_customer_and_address(raw_billing_data, raw_shipping_data, customer_name)
	try:
		site_domain = urlparse(order.get("_links")["self"][0]["href"]).netloc
	except Exception:
		error_message = f"{frappe.get_traceback()}\n\n Order Data: \n{str(order.as_dict())}"
		frappe.log_error("WooCommerce Error", error_message)
		raise
	custom_link_items(order.get("line_items"), woocommerce_settings, sys_lang, site_domain)
	custom_create_sales_order(order, woocommerce_settings, customer_docname, sys_lang)

	sales_order = frappe.get_doc("Sales Order", {"woocommerce_id": order.get("id")})
	create_and_link_payment_entry(order, sales_order.name)


def create_and_link_payment_entry(wc_order, sales_order_name):
	"""
	Create a Payment Entry for WooCommerce Orders that has been marked as Paid
	"""
	# Fetch WooCommerce Additional Settings
	woocommerce_additional_settings = frappe.get_single("WooCommerce Additional Settings")

	try:
		sales_order = frappe.get_doc("Sales Order", sales_order_name)
		wc_server = next(
			(
				server
				for server in woocommerce_additional_settings.servers
				if sales_order.woocommerce_site in server.woocommerce_server_url
			),
			None,
		)
		if not wc_server:
			raise ValueError("Could not find woocommerce_site in list of servers")

		# Validate that WooCommerce order has been paid, and that sales order doesn't have a linked Payment Entry yet
		if (
			wc_server.enable_payments_sync
			and wc_order["payment_method"]
			and wc_order["date_paid"]
			and not sales_order.woocommerce_payment_entry
		):
			# Get Company Bank Account for this Payment Method
			payment_method_bank_account_mapping = json.loads(wc_server.payment_method_bank_account_mapping)
			company_bank_account = payment_method_bank_account_mapping[wc_order["payment_method"]]

			if company_bank_account:
				# Get G/L Account for this Payment Method
				payment_method_gl_account_mapping = json.loads(wc_server.payment_method_gl_account_mapping)
				company_gl_account = payment_method_gl_account_mapping[wc_order["payment_method"]]

				# Create a new Payment Entry
				company = frappe.get_value("Account", company_gl_account, "company")
				meta_data = wc_order.get("meta_data", None)
				payment_reference_no = (
					next(
						(
							data["value"]
							for data in meta_data
							if data["key"] in ("_yoco_payment_id", "_transaction_id")
						),
						None,
					)
					if meta_data and type(meta_data) is list
					else None
				)
				payment_entry_dict = {
					"company": company,
					"payment_type": "Receive",
					"reference_no": payment_reference_no or wc_order["payment_method_title"],
					"reference_date": wc_order["date_paid"],
					"party_type": "Customer",
					"party": sales_order.customer,
					"posting_date": wc_order["date_paid"],
					"paid_amount": sales_order.grand_total,
					"received_amount": sales_order.grand_total,
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
				sales_order.save()

	except Exception:
		frappe.log_error(
			"WooCommerce Sync Task Error",
			f"Failed to create Payment Entry for WooCommerce Order {wc_order['name']}\n{frappe.get_traceback()}",
		)
		return
