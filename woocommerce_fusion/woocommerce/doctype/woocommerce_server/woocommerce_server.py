# Copyright (c) 2023, Dirk van der Laarse and contributors
# For license information, please see license.txt

from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.model.document import Document
from woocommerce import API

from woocommerce_fusion.woocommerce.woocommerce_api import parse_domain_from_url


class WooCommerceServer(Document):
	def autoname(self):
		"""
		Derive name from woocommerce_server_url field
		"""
		self.name = parse_domain_from_url(self.woocommerce_server_url)

	def validate(self):
		# Validate URL
		result = urlparse(self.woocommerce_server_url)
		if not all([result.scheme, result.netloc]):
			frappe.throw(_("Please enter a valid WooCommerce Server URL"))

		# Get Shipment Providers if the "Advanced Shipment Tracking" woocommerce plugin is used
		if self.enable_sync and self.wc_plugin_advanced_shipment_tracking:
			self.get_shipment_providers()

		if not self.secret:
			self.secret = frappe.generate_hash()

	def get_shipment_providers(self):
		"""
		Fetches the names of all shipment providers from a given WooCommerce server.

		This function uses the WooCommerce API to get a list of shipment tracking
		providers. If the request is successful and providers are found, the function
		returns a newline-separated string of all provider names.
		"""

		wc_api = API(
			url=self.woocommerce_server_url,
			consumer_key=self.api_consumer_key,
			consumer_secret=self.api_consumer_secret,
			version="wc/v3",
			timeout=40,
		)
		all_providers = wc_api.get("orders/1/shipment-trackings/providers").json()
		if all_providers:
			provider_names = [provider for country in all_providers for provider in all_providers[country]]
			self.wc_ast_shipment_providers = "\n".join(provider_names)


@frappe.whitelist()
def get_woocommerce_shipment_providers(woocommerce_server_domain):
	"""
	Return the Shipment Providers for a given WooCommerce Server domain
	"""
	wc_servers = frappe.get_all("WooCommerce Server", fields=["name", "woocommerce_server_url"])
	return next(
		(
			wc_server.wc_ast_shipment_providers
			for wc_server in wc_servers
			if woocommerce_server_domain in wc_server.woocommerce_server_url
		),
		[],
	)
