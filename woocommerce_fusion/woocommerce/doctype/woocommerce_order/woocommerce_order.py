# Copyright (c) 2023, Dirk van der Laarse and contributors
# For license information, please see license.txt

import json
from dataclasses import dataclass
from typing import List, Optional
from math import floor
from urllib.parse import urlparse

from woocommerce import API

import frappe
from frappe.model.document import Document

WC_ORDER_DELIMITER = '~'

@dataclass
class WooCommerceAPI:
    """Class for keeping track of a WooCommerce site."""
    api: API
    woocommerce_server_url: str
    wc_plugin_advanced_shipment_tracking: bool


class WooCommerceOrder(Document):

	wc_api_list: Optional[List[WooCommerceAPI]] = None
	current_wc_api: Optional[WooCommerceAPI] = None
	
	def init_api(self):
		"""
		Initialise the WooCommerce API
		"""
		self.wc_api_list = _init_api()

	def db_insert(self, *args, **kwargs):
		"""
		Creates a new WooCommerce Order
		"""
		# Verify that the WC API has been initialised
		if not self.wc_api_list:
			self.init_api()

		# Select the relevant WooCommerce server
		self.current_wc_api = next((
			api for api in self.wc_api_list
				if self.woocommerce_server_url == api.woocommerce_server_url),
			None
		)

		order_data = self.to_dict()

		response = self.current_wc_api.api.post("orders", data=order_data)
		if not response or response.status_code != 201:
			frappe.throw(f"Something went wrong when connecting to WooCommerce: {response.reason} \n {response.text}")


	def load_from_db(self):
		"""
		Returns a single WooCommerce Order (Form view)
		"""
		# Verify that the WC API has been initialised
		if not self.wc_api_list:
			self.init_api()

		# Parse the server domain and order_id from the Document name
		wc_server_domain, order_id = self.name.split(WC_ORDER_DELIMITER)

		# Select the relevant WooCommerce server
		self.current_wc_api = next((
			api for api in self.wc_api_list
				if wc_server_domain in api.woocommerce_server_url),
			None
		)

		# Get WooCommerce Order
		order = self.current_wc_api.api.get(f"orders/{order_id}").json()

		order = self.get_additional_order_attributes(order)
		
		# Remove unused attributes
		order.pop('_links')

		# Map Frappe metadata to WooCommerce
		order['modified'] = order['date_modified']

		# Define woocommerce_server_url
		order['woocommerce_server_url'] = self.current_wc_api.woocommerce_server_url

		# Make sure that all JSON fields are dumped as JSON when returned from the WooCommerce API
		order_with_serialized_subdata = self.serialize_attributes_of_type_dict_or_list(order)

		self.call_super_init(order_with_serialized_subdata)

	def call_super_init(self, order):
		super(Document, self).__init__(order)

	def db_update(self, *args, **kwargs):
		"""
		Updates a WooCommerce Order
		"""
		# Verify that the WC API has been initialised
		if not self.wc_api_list:
			self.init_api()

		# Prepare data
		order_data = self.to_dict()
		order_with_deserialized_subdata = self.deserialize_attributes_of_type_dict_or_list(order_data)
		cleaned_order = self.clean_up_order(order_with_deserialized_subdata)

		# Parse the server domain and order_id from the Document name
		wc_server_domain, order_id = self.name.split(WC_ORDER_DELIMITER)

		# Select the relevant WooCommerce server
		self.current_wc_api = next((
			api for api in self.wc_api_list
				if wc_server_domain in api.woocommerce_server_url),
			None
		)

		# Make API call
		response = self.current_wc_api.api.put(f"orders/{order_id}", data=cleaned_order)
		if not response or response.status_code != 200:
			frappe.throw(f"Something went wrong when connecting to WooCommerce: {response.reason} \n {response.text}")
		
		self.update_shipment_tracking()


	def to_dict(self):
		"""
		Convert this Document to a dict
		"""
		return { field.fieldname: self.get(field.fieldname)
			for field in self.meta.fields
		}

	def serialize_attributes_of_type_dict_or_list(self, obj):
		"""
		Serializes the dictionary and list attributes of a given object into JSON format.
		
		This function iterates over the fields of the input object that are expected to be in JSON format,
		and if the field is present in the object, it transforms the field's value into a JSON-formatted string.
		"""		
		json_fields = self.get_json_fields()
		for field in json_fields:
			if field.fieldname in obj:
				obj[field.fieldname] = json.dumps(obj[field.fieldname])
		return obj

	def deserialize_attributes_of_type_dict_or_list(self, obj):
		"""
		Deserializes the dictionary and list attributes of a given object from JSON format.
		
		This function iterates over the fields of the input object that are expected to be in JSON format,
		and if the field is present in the object, it transforms the field's value from a JSON-formatted string.
		"""	
		json_fields = self.get_json_fields()
		for field in json_fields:
			if field.fieldname in obj and obj[field.fieldname]:
				obj[field.fieldname] = json.loads(obj[field.fieldname])
		return obj

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
				wc_server_domain, order_id = self.name.split(WC_ORDER_DELIMITER)
				order['shipment_trackings'] = self.current_wc_api.api.get(f"orders/{order_id}/shipment-trackings").json()

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
		wc_server_domain, order_id = self.name.split(WC_ORDER_DELIMITER)

		# Select the relevant WooCommerce server
		self.current_wc_api = next((
			api for api in self.wc_api_list
				if wc_server_domain in api.woocommerce_server_url),
			None
		)

		if self.current_wc_api.wc_plugin_advanced_shipment_tracking:

			# Verify if the 'shipment_trackings' field changed
			if self.shipment_trackings != self._doc_before_save.shipment_trackings:
				# Parse JSON
				new_shipment_tracking = json.loads(self.shipment_trackings)

				# Remove the tracking_id key-value pair
				for item in new_shipment_tracking:
					if 'tracking_id' in item:
						item.pop('tracking_id')

				# Only the first shipment_tracking will be used
				tracking_info = new_shipment_tracking[0]
				tracking_info['replace_tracking'] = 1

				# Make the API Call
				response = self.current_wc_api.api.post(f"orders/{order_id}/shipment-trackings/", data=tracking_info)
				if not response or response.status_code != 201:
					frappe.throw(f"Something went wrong when connecting to WooCommerce: {response.reason} \n {response.text}")



	@staticmethod
	def get_list(args):
		"""
		Returns List of WooCommerce Orders (List view and Report view)
		"""
		all_orders = []

		# Initialise the WC API
		wc_api_list = _init_api()
		nr_of_wc_servers = len(wc_api_list)
		if nr_of_wc_servers > 0:
			# Map Frappe query parameters to WooCommerce query parameters
			params = {}
			if args:
				# Adjust query parameters if there are multiple WC servers
				per_page = min(int(args['page_length']), 100)
				per_page = floor(per_page/nr_of_wc_servers)
				offset = int(args['start'])
				offset = floor(offset/nr_of_wc_servers)

				if 'page_length' in args and args['page_length']:
					params['per_page'] = per_page
				if 'start' in args and args['start']:
					params['offset'] = offset
				if 'filters' in args and args['filters']:
					updated_params = get_wc_parameters_from_filters(args['filters'])
					params.update(updated_params)

			for wc_server in wc_api_list:
				# Get WooCommerce Orders
				response = wc_server.api.get("orders", params=params)
				if not response or response.status_code != 200:
					frappe.throw(f"Something went wrong when connecting to WooCommerce: {response.reason} \n {response.text}")
				orders = response.json()

				# Frappe requires a 'name' attribute on each Document. Set this to a combinbation
				# of the WC server domain and the Order ID, e.g. www.mysite.com~69
				# Also add the server URL to the order.
				for order in orders:
					order['name'] = "{domain}{delimiter}{order_id}".format(
						domain=urlparse(wc_server.woocommerce_server_url).netloc,
						delimiter=WC_ORDER_DELIMITER,
						order_id=str(order['id']))
					order['woocommerce_server_url'] = wc_server.woocommerce_server_url
				
				# Append to the list of all orders
				all_orders.extend(orders)

		return all_orders

	@staticmethod
	def get_count(args) -> int:
		"""
		Returns count of WooCommerce Orders (List view and Report view)
		"""
		# Initialise the WC API
		wc_api_list = _init_api()
		total_count = 0

		for wc_server in wc_api_list:
			# Get WooCommerce Orders
			response = wc_server.api.get("orders")
			if not response or response.status_code != 200:
				frappe.throw(f"Something went wrong when connecting to WooCommerce: {response.reason} \n {response.text}")
		
			if 'x-wp-total' in response.headers:
				total_count += int(response.headers['x-wp-total'])
		
		return total_count

	@staticmethod
	def get_stats(args):
		pass

	@staticmethod
	def clean_up_order(order):
		"""
		Perform some tasks to make sure that an order is in the correct format for the WC API
		"""
		# Remove the 'parent_name' attribute if it has a None value,
		# and set the line item's 'image' attribute
		if 'line_items' in order and order['line_items']:
			for line in order['line_items']:
				if 'parent_name' in line and not line['parent_name']:
					line.pop('parent_name')
				if 'image' in line:
					if 'id' in line['image'] and line['image']['id'] == '':
						line.pop('image')

		return order

	@staticmethod
	def get_json_fields():
		"""
		Returns a list of fields that have been defined with type "JSON"
		"""
		fields = frappe.get_list(
			"DocField",
			{
				"parent": "WooCommerce Order",
				"fieldtype": "JSON"
			},
			["name", "fieldname", "fieldtype"]
		)

		return fields

def _init_api() -> List[WooCommerceAPI]:
	"""
	Initialise the WooCommerce API
	"""
	woocommerce_additional_settings = frappe.get_doc("WooCommerce Additional Settings")

	wc_api_list = [
		WooCommerceAPI(
			api=API(url=server.woocommerce_server_url,
					consumer_key=server.api_consumer_key,
					consumer_secret=server.api_consumer_secret,
					version="wc/v3"),
			woocommerce_server_url=server.woocommerce_server_url,
			wc_plugin_advanced_shipment_tracking=server.wc_plugin_advanced_shipment_tracking
		) for server in woocommerce_additional_settings.servers if server.enable_sync == 1
	]

	return wc_api_list

def get_woocommerce_additional_settings():
	return frappe.get_doc("WooCommerce Additional Settings")

def get_wc_parameters_from_filters(filters):
	"""
	http://woocommerce.github.io/woocommerce-rest-api-docs/#list-all-orders
	"""
	supported_filter_fields = ['date_created', 'date_modified']

	params = {}

	for filter in filters:
		if filter[1] not in supported_filter_fields:
			frappe.throw(f"Unsupported filter for field: {filter[1]}")
		if filter[1] == 'date_created' and filter[2] == '<':
			# e.g. ['WooCommerce Order', 'date_created', '<', '2023-01-01']
			params['before'] = filter[3]
			continue
		if filter[1] == 'date_created' and filter[2] == '>':
			# e.g. ['WooCommerce Order', 'date_created', '>', '2023-01-01']
			params['after'] = filter[3]
			continue
		if filter[1] == 'date_modified' and filter[2] == '<':
			# e.g. ['WooCommerce Order', 'date_modified', '<', '2023-01-01']
			params['modified_before'] = filter[3]
			continue
		if filter[1] == 'date_modified' and filter[2] == '>':
			# e.g. ['WooCommerce Order', 'date_modified', '>', '2023-01-01']
			params['modified_after'] = filter[3]
			continue
		frappe.throw(f"Unsupported filter '{filter[2]}' for field {filter[1]}")
	
	return params

