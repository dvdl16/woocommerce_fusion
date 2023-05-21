# Copyright (c) 2023, Dirk van der Laarse and contributors
# For license information, please see license.txt

import json
from woocommerce import API

import frappe
from frappe.model.document import Document

class WooCommerceOrder(Document):

	wcapi = None
	woocommerce_additional_settings = None
	
	def init_api(self):
		"""
		Initialise the WooCommerce API
		"""
		self.wcapi = _init_api()
		self.woocommerce_additional_settings = get_woocommerce_additional_settings()

	def db_insert(self, *args, **kwargs):
		"""
		Creates a new WooCommerce Order
		"""
		# Verify that the WC API has been initialised
		if not self.wcapi:
			self.init_api()

		order_data = self.to_dict()

		response = self.wcapi.post("orders", data=order_data)
		if not response or response.status_code != 201:
			frappe.throw(f"Something went wrong when connecting to WooCommerce: {response.reason} \n {response.text}")


	def load_from_db(self):
		"""
		Returns a single WooCommerce Order (Form view)
		"""
		# Verify that the WC API has been initialised
		if not self.wcapi:
			self.init_api()

		# Get WooCommerce Order
		order = self.wcapi.get(f"orders/{self.name}").json()

		order = self.get_additional_order_attributes(order)
		
		# Remove unused attributes
		order.pop('_links')

		# Map Frappe metadata to WooCommerce
		order['modified'] = order['date_modified']

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
		if not self.wcapi:
			self.init_api()

		# Prepare data
		order_data = self.to_dict()
		order_with_deserialized_subdata = self.deserialize_attributes_of_type_dict_or_list(order_data)
		cleaned_order = self.clean_up_order(order_with_deserialized_subdata)

		# Make API call
		response = self.wcapi.put(f"orders/{self.name}", data=cleaned_order)
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
		if not self.wcapi:
			self.init_api()

		# If the "Advanced Shipment Tracking" WooCommerce Plugin is enabled, make an additional
		# API call to get the tracking information 
		if self.woocommerce_additional_settings:
			if self.woocommerce_additional_settings.wc_plugin_advanced_shipment_tracking:
				order['shipment_trackings'] = self.wcapi.get(f"orders/{self.name}/shipment-trackings").json()

		return order
	
	def update_shipment_tracking(self):
		"""
		Handle fields from "Advanced Shipment Tracking" WooCommerce Plugin
		Replace the current shipment_trackings with shipment_tracking.

		See https://docs.zorem.com/docs/ast-free/add-tracking-to-orders/shipment-tracking-api/#shipment-tracking-properties
		"""
		if self.woocommerce_additional_settings:
			if self.woocommerce_additional_settings.wc_plugin_advanced_shipment_tracking:

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
					response = self.wcapi.post(f"orders/{self.name}/shipment-trackings/", data=tracking_info)
					if not response or response.status_code != 201:
						frappe.throw(f"Something went wrong when connecting to WooCommerce: {response.reason} \n {response.text}")



	@staticmethod
	def get_list(args):
		"""
		Returns List of WooCommerce Orders (List view and Report view)
		"""
		# Initialise the WC API
		wcapi = _init_api()

		# Get WooCommerce Orders
		orders = wcapi.get("orders").json()

		# Frappe requires a 'name' attribute on each Document
		for order in orders:
			order['name'] = order['id']

		return orders

	@staticmethod
	def get_count(args):
		pass

	@staticmethod
	def get_stats(args):
		pass

	@staticmethod
	def clean_up_order(order):
		"""
		Perform some tasks to make sure that an order is in the correct format for the WC API
		"""
		# Remove the 'parent_name' attribute if it has a None value
		if 'line_items' in order and order['line_items']:
			for line in order['line_items']:
				if 'parent_name' in line and not line['parent_name']:
					line.pop('parent_name')

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

def _init_api():
	"""
	Initialise the WooCommerce API
	"""
	woocommerce_settings = frappe.get_doc("Woocommerce Settings")

	wcapi = API(
		url=woocommerce_settings.woocommerce_server_url,
		consumer_key=woocommerce_settings.api_consumer_key,
		consumer_secret=woocommerce_settings.api_consumer_secret,
		version="wc/v3"
	)

	return wcapi

def get_woocommerce_additional_settings():
	return frappe.get_doc("WooCommerce Additional Settings")
