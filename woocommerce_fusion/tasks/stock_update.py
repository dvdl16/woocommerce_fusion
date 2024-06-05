import math

import frappe

from woocommerce_fusion.tasks.utils import APIWithRequestLogging


def update_stock_levels_for_woocommerce_item(doc, method):
	if not frappe.flags.in_test:
		if doc.doctype in ("Stock Entry", "Stock Reconciliation", "Sales Invoice", "Delivery Note"):
			if doc.doctype == "Sales Invoice":
				if doc.update_stock == 0:
					return
			item_codes = [row.item_code for row in doc.items]
			for item_code in item_codes:
				frappe.enqueue(
					"woocommerce_fusion.tasks.stock_update.update_stock_levels_on_woocommerce_site",
					enqueue_after_commit=True,
					item_code=item_code,
				)


def update_stock_levels_for_all_enabled_items_in_background():
	"""
	Get all enabled ERPNext Items and post stock updates to WooCommerce
	"""
	erpnext_items = []
	current_page_length = 500
	start = 0

	# Get all items, 500 records at a time
	while current_page_length == 500:
		items = frappe.db.get_all(
			doctype="Item",
			filters={"disabled": 0},
			fields=["name"],
			start=start,
			page_length=500,
		)
		erpnext_items.extend(items)
		current_page_length = len(items)
		start += current_page_length

	for item in erpnext_items:
		frappe.enqueue(
			"woocommerce_fusion.tasks.stock_update.update_stock_levels_on_woocommerce_site",
			item_code=item.name,
		)


@frappe.whitelist()
def update_stock_levels_on_woocommerce_site(item_code):
	"""
	Updates stock levels of an item on all its associated WooCommerce sites.

	This function fetches the item from the database, then for each associated
	WooCommerce site, it retrieves the current inventory, calculates the new stock quantity,
	and posts the updated stock levels back to the WooCommerce site.
	"""
	item = frappe.get_doc("Item", item_code)

	if len(item.woocommerce_servers) == 0 or not item.is_stock_item or item.disabled:
		return False
	else:
		bins = frappe.get_list(
			"Bin", {"item_code": item_code}, ["name", "warehouse", "reserved_qty", "actual_qty"]
		)

		for wc_site in item.woocommerce_servers:
			woocommerce_id = wc_site.woocommerce_id
			woocommerce_server = wc_site.woocommerce_server
			wc_server = frappe.get_cached_doc("WooCommerce Server", woocommerce_server)

			if not wc_server or not wc_server.enable_sync:
				continue

			wc_api = APIWithRequestLogging(
				url=wc_server.woocommerce_server_url,
				consumer_key=wc_server.api_consumer_key,
				consumer_secret=wc_server.api_consumer_secret,
				version="wc/v3",
				timeout=40,
			)

			# Sum all quantities from all warehouses and round the total down (WooCommerce API doesn't accept float values)
			data_to_post = {"stock_quantity": math.floor(sum(bin.actual_qty for bin in bins))}

			try:
				response = wc_api.put(endpoint=f"products/{woocommerce_id}", data=data_to_post)
			except Exception as err:
				error_message = f"{frappe.get_traceback()}\n\nData in PUT request: \n{str(data_to_post)}"
				frappe.log_error("WooCommerce Error", error_message)
				return False
			if response.status_code != 200:
				error_message = f"Status Code not 200\n\nData in PUT request: \n{str(data_to_post)}"
				error_message += (
					f"\n\nResponse: \n{response.status_code}\nResponse Text: {response.text}\nRequest URL: {response.request.url}\nRequest Body: {response.request.body}"
					if response is not None
					else ""
				)
				frappe.log_error("WooCommerce Error", error_message)
				return False

		return True
