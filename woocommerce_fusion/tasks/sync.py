import frappe
from frappe.utils import get_datetime, now

from woocommerce_fusion.overrides.erpnext_integrations.woocommerce_connection import (
	custom_create_sales_order,
	link_customer_and_address,
	link_items,
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
		wc_order_list = get_list_of_wc_orders(date_time_from, date_time_to)

	# Get list of Sales Orders
	sales_orders = frappe.get_all(
		"Sales Order",
		filters={
			"woocommerce_id": ["in", [order["id"] for order in wc_order_list]],
			"woocommerce_site": ["in", [order["woocommerce_site"] for order in wc_order_list]],
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
			create_sales_order(order, woocommerce_settings)

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


def get_list_of_wc_orders(date_time_from=None, date_time_to=None):
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
		wc_order.save()


def create_sales_order(order, woocommerce_settings):
	"""
	Create an ERPNext Sales Order from the given WooCommerce Order
	"""
	sys_lang = frappe.get_single("System Settings").language or "en"
	raw_billing_data = order.get("billing")
	raw_shipping_data = order.get("shipping")
	customer_name = raw_billing_data.get("first_name") + " " + raw_billing_data.get("last_name")
	customer_docname = link_customer_and_address(raw_billing_data, raw_shipping_data, customer_name)
	link_items(order.get("line_items"), woocommerce_settings, sys_lang)
	custom_create_sales_order(order, woocommerce_settings, customer_docname, sys_lang)
