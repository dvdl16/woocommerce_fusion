# Copyright (c) 2023, Dirk van der Laarse and contributors
# For license information, please see license.txt

import json
from dataclasses import dataclass
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from woocommerce import API

import frappe
from frappe import _
from frappe.model.document import Document

WC_ORDER_DELIMITER = '~'

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
}
WC_ORDER_STATUS_MAPPING_REVERSE = {v: k for k, v in WC_ORDER_STATUS_MAPPING.items()}

@dataclass
class WooCommerceAPI:
	"""Class for keeping track of a WooCommerce site."""
	api: API
	woocommerce_server_url: str
	wc_plugin_advanced_shipment_tracking: bool = False


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

		try:
			response = self.current_wc_api.api.post("orders", data=order_data)
		except Exception as err:
			log_and_raise_error(err)
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
		wc_server_domain, order_id = get_domain_and_id_from_woocommerce_order_name(self.name)

		# Select the relevant WooCommerce server
		self.current_wc_api = next((
			api for api in self.wc_api_list
				if wc_server_domain in api.woocommerce_server_url),
			None
		)

		# Get WooCommerce Order
		try:
			order = self.current_wc_api.api.get(f"orders/{order_id}").json()
		except Exception as err:
			log_and_raise_error(err)

		order = self.get_additional_order_attributes(order)
		
		# Remove unused attributes
		order.pop('_links')

		# Map Frappe metadata to WooCommerce
		order['modified'] = order['date_modified']

		# Define woocommerce_server_url
		server_domain = parse_domain_from_url(self.current_wc_api.woocommerce_server_url)
		order['woocommerce_site'] = server_domain

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
		wc_server_domain, order_id = get_domain_and_id_from_woocommerce_order_name(self.name)

		# Select the relevant WooCommerce server
		self.current_wc_api = next((
			api for api in self.wc_api_list
				if wc_server_domain in api.woocommerce_server_url),
			None
		)

		# Make API call
		try:
			response = self.current_wc_api.api.put(f"orders/{order_id}", data=cleaned_order)
		except Exception as err:
			log_and_raise_error(err)
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
				wc_server_domain, order_id = get_domain_and_id_from_woocommerce_order_name(self.name)
				try:
					order['shipment_trackings'] = self.current_wc_api.api.get(f"orders/{order_id}/shipment-trackings").json()
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
		wc_server_domain, order_id = get_domain_and_id_from_woocommerce_order_name(self.name)

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
				try:
					response = self.current_wc_api.api.post(f"orders/{order_id}/shipment-trackings/", data=tracking_info)
				except Exception as err:
					log_and_raise_error(err)
				if not response or response.status_code != 201:
					frappe.throw(f"Something went wrong when connecting to WooCommerce: {response.reason} \n {response.text}")



	@staticmethod
	def get_list(args):
		"""
		Returns List of WooCommerce Orders (List view and Report view).

		First make a single API call for each API in the list and check if its total record count
		falls within the required range. If not, we adjust the offset for the next API and
		continue to the next one. Otherwise, we start retrieving the required records.
		"""
		# Initialise the WC API
		wc_api_list = _init_api()

		if len(wc_api_list) > 0:
			wc_records_per_page_limit = 100

			# Map Frappe query parameters to WooCommerce query parameters
			params = {}
			per_page = min(int(args['page_length']), wc_records_per_page_limit) \
				if args and 'page_length' in args else wc_records_per_page_limit
			offset = int(args['start']) if args and 'start' in args else 0
			params['per_page'] = min(per_page + offset, wc_records_per_page_limit)

			# Map Frappe filters to WooCommerce parameters
			if 'filters' in args and args['filters']:
				updated_params = get_wc_parameters_from_filters(args['filters'])
				params.update(updated_params)

			# Initialse required variables
			all_results = []
			total_processed = 0

			for wc_server in wc_api_list:	
				current_offset = 0

				# Get WooCommerce Orders
				params['offset'] = current_offset
				try:
					response = wc_server.api.get("orders", params=params)
				except Exception as err:
					log_and_raise_error(err)
				if not response or response.status_code != 200:
					frappe.throw(f"Something went wrong when connecting to WooCommerce: {response.reason} \n {response.text}")
				
				# Store the count of total orders in this API
				count_of_total_records_in_api = int(response.headers['x-wp-total'])

				# Skip this API if all its records fall before the required offset
				if count_of_total_records_in_api <= offset - total_processed:
					total_processed += count_of_total_records_in_api
					continue

				# Parse the response
				results = response.json()

				# If we're still here, it means that this API has some records in the required range
				while True:
					if len(all_results) >= per_page:
						return all_results

					# Adjust indices based on remaining offset and records to collect
					start = max(0, offset - total_processed)
					end = min(len(results), per_page - len(all_results) + start)

					# Add frappe fields to orders
					for order in results[start:end]:
						server_domain = parse_domain_from_url(wc_server.woocommerce_server_url)
						order['name'] = generate_woocommerce_order_name_from_domain_and_id(
							domain=server_domain,
							order_id=order['id']
						)
						order['woocommerce_site'] = server_domain

					all_results.extend(results[start:end])
					total_processed += len(results)
					
					# Check if there are no more records available or required
					if len(results) < per_page:
						break

					current_offset += params['per_page']
					
					# Get WooCommerce Orders
					params['offset'] = current_offset
					try:
						response = wc_server.api.get("orders", params=params)
					except Exception as err:
						log_and_raise_error(err)
					if not response or response.status_code != 200:
						frappe.throw(f"Something went wrong when connecting to WooCommerce: {response.reason} \n {response.text}")
					results = response.json()

			return all_results

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
			try:
				response = wc_server.api.get("orders")
			except Exception as err:
				log_and_raise_error(err)
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
					version="wc/v3",
					timeout=40),
			woocommerce_server_url=server.woocommerce_server_url,
			wc_plugin_advanced_shipment_tracking=server.wc_plugin_advanced_shipment_tracking
		) for server in woocommerce_additional_settings.servers if server.enable_sync == 1
	]

	return wc_api_list

def get_woocommerce_additional_settings():
	return frappe.get_doc("WooCommerce Additional Settings")

def generate_woocommerce_order_name_from_domain_and_id(
		domain: str,
		order_id: int,
		delimiter:str = WC_ORDER_DELIMITER
	) -> str:
	"""
	Generate a name for a woocommerce_order, based on domain and order_id.

	E.g. "site1.example.com~11"
	"""
	return "{domain}{delimiter}{order_id}".format(
		domain=domain,
		delimiter=delimiter,
		order_id=str(order_id)
	)

def get_domain_and_id_from_woocommerce_order_name(
		name: str,
		delimiter:str = WC_ORDER_DELIMITER
	) -> Tuple[str, int]:
	"""
	Get domain and order_id from woocommerce_order name

	E.g. "site1.example.com~11" returns "site1.example.com" and 11
	"""
	domain, order_id = name.split(delimiter)
	return domain, int(order_id)

def get_wc_parameters_from_filters(filters):
	"""
	http://woocommerce.github.io/woocommerce-rest-api-docs/#list-all-orders
	"""
	supported_filter_fields = ['date_created', 'date_modified', 'name']

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
		if filter[1] == 'name' and filter[2] == '=':
			# e.g. ['WooCommerce Order', 'name', '=', '11']
			# params['include'] = [filter[3]]
			params['include'] = [13]
			continue
		frappe.throw(f"Unsupported filter '{filter[2]}' for field '{filter[1]}'")
	
	return params

def parse_domain_from_url(url: str):
	return urlparse(url).netloc


def log_and_raise_error(err):
	"""
	Create an "Error Log" and raise error
	"""
	log = frappe.log_error("WooCommerce Error")
	log_link = frappe.utils.get_link_to_form("Error Log", log.name)
	frappe.throw(
		msg=_("Something went wrong while connecting to WooCommerce. See Error Log {0}").format(log_link), title=_("WooCommerce Error")
	)
	raise err