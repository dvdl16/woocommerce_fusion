from __future__ import unicode_literals

import frappe
from frappe.utils.fixtures import sync_fixtures


@frappe.whitelist()
def execute():
	"""
	Updates the woocommerce_server field on all relevant doctypes
	"""
	# Sync fixtures to ensure that the custom fields `woocommerce_server` exist
	frappe.reload_doc("woocommerce", "doctype", "WooCommerce Server")
	frappe.reload_doc("woocommerce", "doctype", "WooCommerce Additional Settings")
	frappe.reload_doc("woocommerce", "doctype", "Item WooCommerce Server")
	sync_fixtures("woocommerce_fusion")

	# Update WooCommerce Additional Settings
	woocommerce_additional_settings = frappe.get_single("WooCommerce Additional Settings")
	print("Updating WooCommerce Additional Settings...")
	for wc_server in woocommerce_additional_settings.servers:
		print(f"Updating {wc_server.woocommerce_server_url}")
		woocommerce_server = frappe.new_doc("WooCommerce Server")
		woocommerce_server.woocommerce_server_url = wc_server.woocommerce_server_url
		woocommerce_server.save()
		wc_server.woocommerce_server = woocommerce_server.name
	woocommerce_additional_settings.save()

	# Update Customers
	frappe.db.sql("""UPDATE `tabCustomer` SET woocommerce_server=woocommerce_site""")

	# Update Sales Orders
	frappe.db.sql("""UPDATE `tabSales Order` SET woocommerce_server=woocommerce_site""")

	# Update Addresses
	frappe.db.sql("""UPDATE `tabAddress` SET woocommerce_server=woocommerce_site""")

	# Update Items
	frappe.db.sql("""UPDATE `tabItem WooCommerce Server` SET woocommerce_server=woocommerce_site""")

	frappe.db.commit()
