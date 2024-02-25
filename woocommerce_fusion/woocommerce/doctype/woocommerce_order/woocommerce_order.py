# Copyright (c) 2023, Dirk van der Laarse and contributors
# For license information, please see license.txt

import json
from dataclasses import dataclass
from typing import Dict, List

import frappe

from woocommerce_fusion.tasks.utils import APIWithRequestLogging
from woocommerce_fusion.woocommerce.woocommerce_api import (
	WooCommerceAPI,
	WooCommerceResource,
	get_domain_and_id_from_woocommerce_record_name,
	log_and_raise_error,
)

WC_ORDER_DELIMITER = "~"

WC_ORDER_STATUS_MAPPING = {
	"Pending Payment": "pending",
	"On hold": "on-hold",
	"Failed": "failed",
	"Cancelled": "cancelled",
	"Processing": "processing",
	"Refunded": "refunded",
	"Shipped": "completed",
	"Ready for Pickup": "ready-pickup",
	"Picked up": "pickup",
	"Delivered": "delivered",
	"Processing LP": "processing-lp",
	"Draft": "checkout-draft",
	"Quote Sent": "gplsquote-req",
	"Trash": "trash",
}
WC_ORDER_STATUS_MAPPING_REVERSE = {v: k for k, v in WC_ORDER_STATUS_MAPPING.items()}


@dataclass
class WooCommerceOrderAPI(WooCommerceAPI):
	"""Class for keeping track of a WooCommerce site."""

	wc_plugin_advanced_shipment_tracking: bool = False


class WooCommerceOrder(WooCommerceResource):
	"""
	Virtual doctype for WooCommerce Orders
	"""

	resource: str = "orders"

	@staticmethod
	def _init_api() -> List[WooCommerceAPI]:
		"""
		Initialise the WooCommerce API
		"""
		woocommerce_integration_settings = frappe.get_single("WooCommerce Integration Settings")

		wc_api_list = [
			WooCommerceOrderAPI(
				api=APIWithRequestLogging(
					url=server.woocommerce_server_url,
					consumer_key=server.api_consumer_key,
					consumer_secret=server.api_consumer_secret,
					version="wc/v3",
					timeout=40,
				),
				woocommerce_server_url=server.woocommerce_server_url,
				woocommerce_server=server.woocommerce_server,
				wc_plugin_advanced_shipment_tracking=server.wc_plugin_advanced_shipment_tracking,
			)
			for server in woocommerce_integration_settings.servers
			if server.enable_sync == 1
		]

		return wc_api_list

	# use "args" despite frappe-semgrep-rules.rules.overusing-args, following convention in ERPNext
	# nosemgrep
	@staticmethod
	def get_list(args):
		return WooCommerceOrder.get_list_of_records(args)

	def after_load_from_db(self, order: Dict):
		return self.get_additional_order_attributes(order)

	# use "args" despite frappe-semgrep-rules.rules.overusing-args, following convention in ERPNext
	# nosemgrep
	@staticmethod
	def get_count(args) -> int:
		return WooCommerceOrder.get_count_of_records(args)

	def before_db_update(self, order: Dict):
		cleaned_order = self.clean_up_order(order)

		# Drop all fields except for 'status' and 'shipment_trackings'
		keys_to_pop = [
			key for key in cleaned_order.keys() if key not in ("status", "shipment_trackings")
		]
		for key in keys_to_pop:
			cleaned_order.pop(key)

		return cleaned_order

	def after_db_update(self):
		self.update_shipment_tracking()

	def get_additional_order_attributes(self, order):
		"""
		Make API calls to WC to get additional order attributes, such as Tracking Data
		managed by an additional WooCommerce plugin
		"""
		# Verify that the WC API has been initialised
		if self.current_wc_api:
			# If the "Advanced Shipment Tracking" WooCommerce Plugin is enabled, make an additional
			# API call to get the tracking information
			if self.current_wc_api.wc_plugin_advanced_shipment_tracking:
				wc_server_domain, order_id = get_domain_and_id_from_woocommerce_record_name(self.name)
				try:
					order["shipment_trackings"] = self.current_wc_api.api.get(
						f"orders/{order_id}/shipment-trackings"
					).json()
				except Exception as err:
					log_and_raise_error(err)

		return order

	def update_shipment_tracking(self):
		"""
		Handle fields from "Advanced Shipment Tracking" WooCommerce Plugin
		Replace the current shipment_trackings with shipment_tracking.

		See https://docs.zorem.com/docs/ast-free/add-tracking-to-orders/shipment-tracking-api/#shipment-tracking-properties
		"""
		# Verify that the WC API has been initialised
		if not self.wc_api_list:
			self.init_api()

		# Parse the server domain and order_id from the Document name
		wc_server_domain, order_id = get_domain_and_id_from_woocommerce_record_name(self.name)

		# Select the relevant WooCommerce server
		self.current_wc_api = next(
			(api for api in self.wc_api_list if wc_server_domain in api.woocommerce_server_url), None
		)

		if self.current_wc_api.wc_plugin_advanced_shipment_tracking:

			# Verify if the 'shipment_trackings' field changed
			if self.shipment_trackings != self._doc_before_save.shipment_trackings:
				# Parse JSON
				new_shipment_tracking = json.loads(self.shipment_trackings)

				# Remove the tracking_id key-value pair
				for item in new_shipment_tracking:
					if "tracking_id" in item:
						item.pop("tracking_id")

				# Only the first shipment_tracking will be used
				tracking_info = new_shipment_tracking[0]
				tracking_info["replace_tracking"] = 1

				# Make the API Call
				try:
					response = self.current_wc_api.api.post(
						f"orders/{order_id}/shipment-trackings/", data=tracking_info
					)
				except Exception as err:
					log_and_raise_error(err, error_text="update_shipment_tracking failed")
				if response.status_code != 201:
					log_and_raise_error(error_text="update_shipment_tracking failed", response=response)

	@staticmethod
	def clean_up_order(order):
		"""
		Perform some tasks to make sure that an order is in the correct format for the WC API
		"""
		# Remove the 'parent_name' attribute if it has a None value,
		# and set the line item's 'image' attribute
		if "line_items" in order and order["line_items"]:
			for line in order["line_items"]:
				if "parent_name" in line and not line["parent_name"]:
					line.pop("parent_name")
				if "image" in line:
					if "id" in line["image"] and line["image"]["id"] == "":
						line.pop("image")

		# Remove the read-only `display_value` and `display_key` attributes as per
		# https://github.com/woocommerce/woocommerce/issues/32038#issuecomment-1117140390
		# This avoids HTTP 400 errors when updating orders, e.g. "line_items[0][meta_data][0][display_value] is not of type string"
		if "line_items" in order and order["line_items"]:
			for line in order["line_items"]:
				if "meta_data" in line:
					for meta in line["meta_data"]:
						if "display_key" in meta:
							meta.pop("display_key")
						if "display_value" in meta:
							meta.pop("display_value")

		return order
