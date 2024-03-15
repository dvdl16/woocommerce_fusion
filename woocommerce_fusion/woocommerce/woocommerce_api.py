import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.model.document import Document

from woocommerce_fusion.tasks.utils import APIWithRequestLogging

WC_RESOURCE_DELIMITER = "~"


@dataclass
class WooCommerceAPI:
	"""Class for keeping track of a WooCommerce site."""

	api: APIWithRequestLogging
	woocommerce_server_url: str
	woocommerce_server: str


class WooCommerceResource(Document):

	wc_api_list: Optional[List[WooCommerceAPI]] = None
	current_wc_api: Optional[WooCommerceAPI] = None

	resource: str = None
	field_setter_map: Dict = None

	@staticmethod
	def _init_api() -> List[WooCommerceAPI]:
		"""
		Initialise the WooCommerce API
		"""
		woocommerce_integration_settings = frappe.get_single("WooCommerce Integration Settings")

		wc_api_list = [
			WooCommerceAPI(
				api=APIWithRequestLogging(
					url=server.woocommerce_server_url,
					consumer_key=server.api_consumer_key,
					consumer_secret=server.api_consumer_secret,
					version="wc/v3",
					timeout=40,
				),
				woocommerce_server_url=server.woocommerce_server_url,
				woocommerce_server=server.woocommerce_server,
			)
			for server in woocommerce_integration_settings.servers
			if server.enable_sync == 1
		]

		return wc_api_list

	def init_api(self):
		"""
		Initialise the WooCommerce API
		"""
		self.wc_api_list = self._init_api()

	def load_from_db(self):
		"""
		Returns a single WooCommerce Record (Form view)
		"""
		# Verify that the WC API has been initialised
		if not self.wc_api_list:
			self.init_api()

		# Parse the server domain and record_id from the Document name
		wc_server_domain, record_id = get_domain_and_id_from_woocommerce_record_name(self.name)

		# Select the relevant WooCommerce server
		self.current_wc_api = next(
			(api for api in self.wc_api_list if wc_server_domain in api.woocommerce_server_url), None
		)

		# Get WooCommerce Record
		try:
			record = self.current_wc_api.api.get(f"{self.resource}/{record_id}").json()
		except Exception as err:
			error_text = (
				f"load_from_db failed (WooCommerce {self.resource} #{record_id})\n\n{frappe.get_traceback()}"
			)
			log_and_raise_error(error_text)

		if "id" not in record:
			log_and_raise_error(
				error_text=f"load_from_db failed (WooCommerce {self.resource} #{record_id})\nOrder:\n{str(record)}"
			)

		if self.field_setter_map:
			for new_key, old_key in self.field_setter_map.items():
				record[new_key] = record[old_key]

		record = self.after_load_from_db(record)

		# Remove unused attributes
		record.pop("_links")

		# Map Frappe metadata to WooCommerce
		record["modified"] = record["date_modified"]

		# Define woocommerce_server_url
		server_domain = parse_domain_from_url(self.current_wc_api.woocommerce_server_url)
		record["woocommerce_server"] = server_domain

		# Make sure that all JSON fields are dumped as JSON when returned from the WooCommerce API
		record_with_serialized_subdata = self.serialize_attributes_of_type_dict_or_list(record)

		self.call_super_init(record_with_serialized_subdata)

	def call_super_init(self, record: Dict):
		super(Document, self).__init__(record)

	def after_load_from_db(self, record: Dict):
		return record

	@classmethod
	def get_list_of_records(cls, args):
		"""
		Returns List of WooCommerce Records (List view and Report view).

		First make a single API call for each API in the list and check if its total record count
		falls within the required range. If not, we adjust the offset for the next API and
		continue to the next one. Otherwise, we start retrieving the required records.
		"""
		# Initialise the WC API
		wc_api_list = cls._init_api()

		if len(wc_api_list) > 0:
			wc_records_per_page_limit = 100

			# Map Frappe query parameters to WooCommerce query parameters
			params = {}
			per_page = (
				min(int(args["page_length"]), wc_records_per_page_limit)
				if args and "page_length" in args
				else wc_records_per_page_limit
			)
			offset = int(args["start"]) if args and "start" in args else 0
			params["per_page"] = min(per_page + offset, wc_records_per_page_limit)

			# Map Frappe filters to WooCommerce parameters
			if "filters" in args and args["filters"]:
				updated_params = get_wc_parameters_from_filters(args["filters"])
				params.update(updated_params)

			# Initialse required variables
			all_results = []
			total_processed = 0

			for wc_server in wc_api_list:
				current_offset = 0

				# Get WooCommerce Records
				params["offset"] = current_offset
				try:
					response = wc_server.api.get(cls.resource, params=params)
				except Exception as err:
					log_and_raise_error(err, error_text="get_list failed")
				if response.status_code != 200:
					log_and_raise_error(error_text="get_list failed", response=response)

				# Store the count of total records in this API
				count_of_total_records_in_api = int(response.headers["x-wp-total"])

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

					# Add frappe fields to records
					for record in results[start:end]:

						if cls.field_setter_map:
							for new_key, old_key in cls.field_setter_map.items():
								record[new_key] = record[old_key]

						server_domain = parse_domain_from_url(wc_server.woocommerce_server_url)
						record["name"] = generate_woocommerce_record_name_from_domain_and_id(
							domain=server_domain, resource_id=record["id"]
						)
						record["woocommerce_server"] = server_domain
						record = cls.during_get_list_of_records(record)

					all_results.extend(results[start:end])
					total_processed += len(results)

					# Check if there are no more records available or required
					if len(results) < per_page:
						break

					current_offset += params["per_page"]

					# Get WooCommerce Records
					params["offset"] = current_offset
					try:
						response = wc_server.api.get(cls.resource, params=params)
					except Exception as err:
						log_and_raise_error(err, error_text="get_list failed")
					if response.status_code != 200:
						log_and_raise_error(error_text="get_list failed", response=response)
					results = response.json()

			return all_results

	@classmethod
	def during_get_list_of_records(cls, record: Dict):
		return record

	# use "args" despite frappe-semgrep-rules.rules.overusing-args, following convention in ERPNext
	# nosemgrep
	@classmethod
	def get_count_of_records(cls, args) -> int:
		"""
		Returns count of WooCommerce Records (List view and Report view)
		"""
		# Initialise the WC API
		wc_api_list = cls._init_api()
		total_count = 0

		for wc_server in wc_api_list:
			# Get WooCommerce Records
			try:
				response = wc_server.api.get(cls.resource)
			except Exception as err:
				log_and_raise_error(err, error_text="get_count failed")
			if response.status_code != 200:
				log_and_raise_error(error_text="get_count failed", response=response)

			if "x-wp-total" in response.headers:
				total_count += int(response.headers["x-wp-total"])

		return total_count

	# use "args" despite frappe-semgrep-rules.rules.overusing-args, following convention in ERPNext
	# nosemgrep
	@staticmethod
	def get_stats(args):
		pass

	def db_insert(self, *args, **kwargs):
		"""
		Creates a new WooCommerce Record
		"""
		# Verify that the WC API has been initialised
		if not self.wc_api_list:
			self.init_api()

		# Select the relevant WooCommerce server
		self.current_wc_api = next(
			(api for api in self.wc_api_list if self.woocommerce_server == api.woocommerce_server),
			None,
		)

		record_data = self.to_dict()

		record = self.before_db_insert(record_data)

		try:
			response = self.current_wc_api.api.post(self.resource, data=record_data)
		except Exception as err:
			log_and_raise_error(err, error_text="db_insert failed")
		if response.status_code != 201:
			log_and_raise_error(error_text="db_insert failed", response=response)

	def before_db_insert(self, record: Dict):
		return record

	def db_update(self, *args, **kwargs):
		"""
		Updates a WooCommerce Record.

		Note: Only the 'status' and 'shipment_trackings' fields will be updated.
		"""
		# Verify that the WC API has been initialised
		if not self.wc_api_list:
			self.init_api()

		# Prepare data
		record_data = self.to_dict()
		record = self.deserialize_attributes_of_type_dict_or_list(record_data)

		record = self.before_db_update(record)

		# Drop fields with values that are unchanged
		record_data_before_save = self._doc_before_save.to_dict()
		record_before_save = self.deserialize_attributes_of_type_dict_or_list(record_data_before_save)
		if self.field_setter_map:
			for new_key, old_key in self.field_setter_map.items():
				record_before_save[old_key] = record_before_save[new_key]
		keys_to_pop = [
			key
			for key, value in record.items()
			if record_before_save.get(key) == value or str(record_before_save.get(key)) == str(value)
		]
		for key in keys_to_pop:
			record.pop(key)

		# Parse the server domain and order_id from the Document name
		wc_server_domain, order_id = get_domain_and_id_from_woocommerce_record_name(self.name)

		# Select the relevant WooCommerce server
		self.current_wc_api = next(
			(api for api in self.wc_api_list if wc_server_domain in api.woocommerce_server_url), None
		)

		# Make API call
		try:
			response = self.current_wc_api.api.put(f"{self.resource}/{order_id}", data=record)
		except Exception as err:
			log_and_raise_error(err, error_text="db_update failed")
		if response.status_code != 200:
			log_and_raise_error(error_text="db_update failed", response=response)

		self.after_db_update()

	def before_db_update(self, record: Dict):
		return record

	def after_db_update(self):
		pass

	def delete(self):
		frappe.throw(_("Deleting resources have not been implemented yet"))

	def to_dict(self):
		"""
		Convert this Document to a dict
		"""
		return {field.fieldname: self.get(field.fieldname) for field in self.meta.fields}

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

	def get_json_fields(self):
		"""
		Returns a list of fields that have been defined with type "JSON"
		"""
		fields = frappe.db.get_all(
			"DocField",
			{"parent": self.doctype, "fieldtype": "JSON"},
			["name", "fieldname", "fieldtype"],
		)

		return fields


def generate_woocommerce_record_name_from_domain_and_id(
	domain: str, resource_id: int, delimiter: str = WC_RESOURCE_DELIMITER
) -> str:
	"""
	Generate a name for a woocommerce resource, based on domain and resource_id.

	E.g. "site1.example.com~11"
	"""
	return "{domain}{delimiter}{resource_id}".format(
		domain=domain, delimiter=delimiter, resource_id=str(resource_id)
	)


def get_wc_parameters_from_filters(filters):
	"""
	http://woocommerce.github.io/woocommerce-rest-api-docs/#list-all-orders
	https://woocommerce.github.io/woocommerce-rest-api-docs/#list-all-products
	"""
	supported_filter_fields = ["date_created", "date_modified", "id", "name", "status"]

	params = {}

	for filter in filters:
		if filter[1] not in supported_filter_fields:
			frappe.throw(f"Unsupported filter for field: {filter[1]}")
		if filter[1] == "date_created" and filter[2] == "<":
			# e.g. ['WooCommerce Order', 'date_created', '<', '2023-01-01']
			params["before"] = filter[3]
			continue
		if filter[1] == "date_created" and filter[2] == ">":
			# e.g. ['WooCommerce Order', 'date_created', '>', '2023-01-01']
			params["after"] = filter[3]
			continue
		if filter[1] == "date_modified" and filter[2] == "<":
			# e.g. ['WooCommerce Order', 'date_modified', '<', '2023-01-01']
			params["modified_before"] = filter[3]
			continue
		if filter[1] == "date_modified" and filter[2] == ">":
			# e.g. ['WooCommerce Order', 'date_modified', '>', '2023-01-01']
			params["modified_after"] = filter[3]
			continue
		if filter[1] == "id" and filter[2] == "=":
			# e.g. ['WooCommerce Order', 'id', '=', '11']
			params["include"] = [filter[3]]
			continue
		if filter[1] == "id" and filter[2] == "in":
			# e.g. ['WooCommerce Order', 'id', 'in', ['11', '12', '13']]
			params["include"] = ",".join(filter[3])
			continue
		if filter[1] == "name" and filter[2] == "like":
			# e.g. ['WooCommerce Order', 'name', 'like', '%11%']
			params["search"] = filter[3].strip("%")
			continue
		if filter[1] == "status" and filter[2] == "=":
			# e.g. ['WooCommerce Order', 'status', '=', 'trash']
			params["status"] = filter[3]
			continue
		frappe.throw(f"Unsupported filter '{filter[2]}' for field '{filter[1]}'")

	return params


def log_and_raise_error(exception=None, error_text=None, response=None):
	"""
	Create an "Error Log" and raise error
	"""
	error_message = frappe.get_traceback() if exception else ""
	error_message += f"\n{error_text}" if error_text else ""
	error_message += (
		f"\nResponse Code: {response.status_code}\nResponse Text: {response.text}\nRequest URL: {response.request.url}\nRequest Body: {response.request.body}"
		if response is not None
		else ""
	)
	log = frappe.log_error("WooCommerce Error", error_message)
	log_link = frappe.utils.get_link_to_form("Error Log", log.name)
	frappe.throw(
		msg=_("Something went wrong while connecting to WooCommerce. See Error Log {0}").format(
			log_link
		),
		title=_("WooCommerce Error"),
	)
	if exception:
		raise exception


def parse_domain_from_url(url: str):
	return urlparse(url).netloc


def get_domain_and_id_from_woocommerce_record_name(
	name: str, delimiter: str = WC_RESOURCE_DELIMITER
) -> Tuple[str, int]:
	"""
	Get domain and record_id from woocommerce_order name

	E.g. "site1.example.com~11" returns "site1.example.com" and 11
	"""
	domain, record_id = name.split(delimiter)
	return domain, int(record_id)
