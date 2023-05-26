import json
from urllib.parse import urlparse

import frappe

from erpnext.erpnext_integrations.connectors.woocommerce_connection import (
	verify_request,
	link_customer_and_address,
	link_items,
	set_items_in_sales_order
)

from woocommerce_fusion.woocommerce.doctype.woocommerce_order.woocommerce_order \
	import WC_ORDER_STATUS_MAPPING_REVERSE


@frappe.whitelist(allow_guest=True)
def custom_order(*args, **kwargs):
	"""
	Overrided version of erpnext.erpnext_integrations.connectors.woocommerce_connection.order
	in order to populate our custom fields when a Webhook is received
	"""
	try:
		# ==================================== Custom code starts here ==================================== #
		# Original code
		# _order(*args, **kwargs)
		_custom_order(*args, **kwargs)
		# ==================================== Custom code starts here ==================================== #
	except Exception:
		error_message = (
			frappe.get_traceback() + "\n\n Request Data: \n" + json.loads(frappe.request.data).__str__()
		)
		frappe.log_error("WooCommerce Error", error_message)
		raise


def _custom_order(*args, **kwargs):
	"""
	Overrided version of erpnext.erpnext_integrations.connectors.woocommerce_connection._order
	in order to populate our custom fields when a Webhook is received
	"""
	woocommerce_settings = frappe.get_doc("Woocommerce Settings")
	if frappe.flags.woocomm_test_order_data:
		order = frappe.flags.woocomm_test_order_data
		event = "created"

	elif frappe.request and frappe.request.data:
		verify_request()
		try:
			order = json.loads(frappe.request.data)
		except ValueError:
			# woocommerce returns 'webhook_id=value' for the first request which is not JSON
			order = frappe.request.data
		event = frappe.get_request_header("X-Wc-Webhook-Event")

	else:
		return "success"

	if event == "created":
		sys_lang = frappe.get_single("System Settings").language or "en"
		raw_billing_data = order.get("billing")
		raw_shipping_data = order.get("shipping")
		customer_name = raw_billing_data.get("first_name") + " " + raw_billing_data.get("last_name")
		link_customer_and_address(raw_billing_data, raw_shipping_data, customer_name)
		link_items(order.get("line_items"), woocommerce_settings, sys_lang)
		# ==================================== Custom code starts here ==================================== #
		# Original code
		# create_sales_order(order, woocommerce_settings, customer_name, sys_lang)
		custom_create_sales_order(order, woocommerce_settings, customer_name, sys_lang)
		# ==================================== Custom code ends here ==================================== #

def custom_create_sales_order(order, woocommerce_settings, customer_name, sys_lang):
	"""
	Overrided version of erpnext.erpnext_integrations.connectors.woocommerce_connection.create_sales_order
	in order to populate our custom fields when a Webhook is received
	"""
	new_sales_order = frappe.new_doc("Sales Order")
	new_sales_order.customer = customer_name

	new_sales_order.po_no = new_sales_order.woocommerce_id = order.get("id")


	# ==================================== Custom code starts here ==================================== #
	try:
		site_domain = urlparse(order.get("_links")['self'][0]['href']).netloc
	except Exception:
		error_message = (
			frappe.get_traceback() + "\n\n Order Data: \n" + order.__str__()
		)
		frappe.log_error("WooCommerce Error", error_message)
		raise
	new_sales_order.woocommerce_site = site_domain
	new_sales_order.woocommerce_status = WC_ORDER_STATUS_MAPPING_REVERSE[order.get("status")]
	# ==================================== Custom code ends here ==================================== #


	new_sales_order.naming_series = woocommerce_settings.sales_order_series or "SO-WOO-"

	created_date = order.get("date_created").split("T")
	new_sales_order.transaction_date = created_date[0]
	delivery_after = woocommerce_settings.delivery_after_days or 7
	new_sales_order.delivery_date = frappe.utils.add_days(created_date[0], delivery_after)

	new_sales_order.company = woocommerce_settings.company

	set_items_in_sales_order(new_sales_order, woocommerce_settings, order, sys_lang)
	new_sales_order.flags.ignore_mandatory = True
	new_sales_order.insert()
	new_sales_order.submit()

	frappe.db.commit()