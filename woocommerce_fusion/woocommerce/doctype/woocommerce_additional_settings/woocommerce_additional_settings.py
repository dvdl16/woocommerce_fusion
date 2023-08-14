# Copyright (c) 2023, Dirk van der Laarse and contributors
# For license information, please see license.txt
import frappe
from frappe.model.document import Document
from woocommerce import API


class WooCommerceAdditionalSettings(Document):
	def validate(self):
		# Loop through servers and get Shipment Providers if the "Advanced Shipment Tracking"
		# woocommerce plugin is used
		for wc_server in self.servers:
			if wc_server.wc_plugin_advanced_shipment_tracking:
				wc_server.wc_ast_shipment_providers = get_shipment_providers(wc_server)


def get_shipment_providers(server):
	"""
	Fetches the names of all shipment providers from a given WooCommerce server.

	This function uses the WooCommerce API to get a list of shipment tracking
	providers. If the request is successful and providers are found, the function
	returns a newline-separated string of all provider names.
	"""

	wc_api = API(
		url=server.woocommerce_server_url,
		consumer_key=server.api_consumer_key,
		consumer_secret=server.api_consumer_secret,
		version="wc/v3",
		timeout=40,
	)
	all_providers = wc_api.get("orders/1/shipment-trackings/providers").json()
	if all_providers:
		provider_names = [provider for country in all_providers for provider in all_providers[country]]
		return "\n".join(provider_names)


@frappe.whitelist()
def get_woocommerce_shipment_providers(woocommerce_server_domain):
	"""
	Return the Shipment Providers for a given WooCommerce Server domain
	"""
	wc_settings = frappe.get_single("WooCommerce Additional Settings")
	return next(
		(
			wc_server.wc_ast_shipment_providers
			for wc_server in wc_settings.servers
			if woocommerce_server_domain in wc_server.woocommerce_server_url
		),
		[],
	)
