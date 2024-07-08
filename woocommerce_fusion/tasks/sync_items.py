import json
from dataclasses import dataclass
from datetime import datetime
from time import sleep
from typing import List, Optional, Tuple

import frappe
from erpnext.stock.doctype.item.item import Item
from frappe import _, _dict
from frappe.query_builder import Criterion
from frappe.utils import get_datetime, now

from woocommerce_fusion.exceptions import SyncDisabledError
from woocommerce_fusion.tasks.sync import SynchroniseWooCommerce
from woocommerce_fusion.woocommerce.doctype.woocommerce_product.woocommerce_product import (
	WooCommerceProduct,
)
from woocommerce_fusion.woocommerce.doctype.woocommerce_server.woocommerce_server import (
	WooCommerceServer,
)
from woocommerce_fusion.woocommerce.woocommerce_api import (
	generate_woocommerce_record_name_from_domain_and_id,
)


def run_item_sync_from_hook(doc, method):
	"""
	Intended to be triggered by a Document Controller hook from Item
	"""
	if doc.doctype == "Item":
		frappe.enqueue(clear_sync_hash_and_run_item_sync, item_code=doc.name)


@frappe.whitelist()
def run_item_sync(
	item_code: Optional[str] = None, woocommerce_product_name: Optional[str] = None, enqueue=False
) -> Tuple[Item, WooCommerceProduct]:
	# Get ERPNext Item and WooCommerce product if they exist
	if woocommerce_product_name:
		woocommerce_product = frappe.get_doc(
			{"doctype": "WooCommerce Product", "name": woocommerce_product_name}
		)
		woocommerce_product.load_from_db()

		# Trigger sync
		sync = SynchroniseItem(woocommerce_product=woocommerce_product)
		if enqueue:
			frappe.enqueue(sync.run)
		else:
			sync.run()

	elif item_code:
		item = frappe.get_doc("Item", item_code)
		if not item.woocommerce_servers:
			frappe.throw(_("No WooCommerce Servers defined for Item {0}").format(item_code))
		for wc_server in item.woocommerce_servers:
			# Trigger sync for every linked server
			sync = SynchroniseItem(
				item=ERPNextItemToSync(item=item, item_woocommerce_server_idx=wc_server.idx)
			)
			if enqueue:
				frappe.enqueue(sync.run)
			else:
				sync.run()

	return (
		sync.item.item if sync and sync.item else None,
		sync.woocommerce_product if sync else None,
	)


def sync_woocommerce_products_modified_since(date_time_from=None):
	"""
	Get list of WooCommerce products modified since date_time_from
	"""
	wc_settings = frappe.get_doc("WooCommerce Integration Settings")

	if not date_time_from:
		date_time_from = wc_settings.wc_last_sync_date_items

	# Validate
	if not date_time_from:
		error_text = _(
			"'Last Items Syncronisation Date' field on 'WooCommerce Integration Settings' is missing"
		)
		frappe.log_error(
			"WooCommerce Items Sync Task Error",
			error_text,
		)
		raise ValueError(error_text)

	wc_products = get_list_of_wc_products(date_time_from=date_time_from)
	for wc_product in wc_products:
		try:
			run_item_sync(woocommerce_product_name=wc_product["name"])
			sleep(1)
		# Skip items with errors, as these exceptions will be logged
		except Exception:
			pass

	wc_settings.reload()
	wc_settings.wc_last_sync_date_items = now()
	wc_settings.flags.ignore_mandatory = True
	wc_settings.save()


@dataclass
class ERPNextItemToSync:
	"""Class for keeping track of an ERPNext Item and the relevant WooCommerce Server to sync to"""

	item: Item
	item_woocommerce_server_idx: int

	@property
	def item_woocommerce_server(self):
		return self.item.woocommerce_servers[self.item_woocommerce_server_idx - 1]


class SynchroniseItem(SynchroniseWooCommerce):
	"""
	Class for managing synchronisation of WooCommerce Product with ERPNext Item
	"""

	def __init__(
		self,
		servers: List[WooCommerceServer | _dict] = None,
		item: Optional[ERPNextItemToSync] = None,
		woocommerce_product: Optional[WooCommerceProduct] = None,
	) -> None:
		super().__init__(servers)
		self.item = item
		self.woocommerce_product = woocommerce_product
		self.settings = frappe.get_cached_doc("WooCommerce Integration Settings")

	def run(self):
		"""
		Run synchronisation
		"""
		# If a WooCommerce ID or Item Code is supplied, find the item and synchronise it
		try:
			self.get_corresponding_item_or_product()
			self.sync_wc_product_with_erpnext_item()
		except SyncDisabledError:
			pass
		except Exception as err:
			woocommerce_product_dict = (
				self.woocommerce_product.as_dict()
				if isinstance(self.woocommerce_product, WooCommerceProduct)
				else self.woocommerce_product
			)
			error_message = f"{frappe.get_traceback()}\n\nItem Data: \n{str(self.item) if self.item else ''}\n\nWC Product Data \n{str(woocommerce_product_dict) if self.woocommerce_product else ''})"
			frappe.log_error("WooCommerce Error", error_message)

	def get_corresponding_item_or_product(self):
		"""
		If we have an ERPNext Item, get the corresponding WooCommerce Product
		If we have a WooCommerce Product, get the corresponding ERPNext Item
		"""
		if (
			self.item and not self.woocommerce_product and self.item.item_woocommerce_server.woocommerce_id
		):
			# Validate that this Item's WooCommerce Server has sync enabled
			wc_server = frappe.get_cached_doc(
				"WooCommerce Server", self.item.item_woocommerce_server.woocommerce_server
			)
			if not wc_server.enable_sync:
				raise SyncDisabledError

			wc_products = get_list_of_wc_products(item=self.item)
			self.woocommerce_product = wc_products[0]

		if self.woocommerce_product and not self.item:
			self.get_erpnext_item()

	def get_erpnext_item(self):
		"""
		Get erpnext item for a WooCommerce Product
		"""
		if not all(
			[self.woocommerce_product.woocommerce_server, self.woocommerce_product.woocommerce_id]
		):
			raise ValueError()

		iws = frappe.qb.DocType("Item WooCommerce Server")
		itm = frappe.qb.DocType("Item")

		and_conditions = [
			iws.enabled == 1,
			iws.woocommerce_server == self.woocommerce_product.woocommerce_server,
			iws.woocommerce_id == self.woocommerce_product.woocommerce_id,
		]

		item_codes = (
			frappe.qb.from_(iws)
			.join(itm)
			.on(iws.parent == itm.name)
			.where(Criterion.all(and_conditions))
			.select(iws.parent, iws.name)
			.limit(1)
		).run(as_dict=True)

		found_item = frappe.get_doc("Item", item_codes[0].parent) if item_codes else None
		if found_item:
			self.item = ERPNextItemToSync(
				item=found_item,
				item_woocommerce_server_idx=next(
					server.idx for server in found_item.woocommerce_servers if server.name == item_codes[0].name
				),
			)

	def sync_wc_product_with_erpnext_item(self):
		"""
		Syncronise Item between ERPNext and WooCommerce
		"""
		if self.item and not self.woocommerce_product:
			# create missing product in WooCommerce
			self.create_woocommerce_product(self.item)
		elif self.woocommerce_product and not self.item:
			# create missing item in ERPNext
			self.create_item(self.woocommerce_product)
		elif self.item and self.woocommerce_product:
			# both exist, check sync hash
			if (
				self.woocommerce_product.woocommerce_date_modified
				!= self.item.item_woocommerce_server.woocommerce_last_sync_hash
			):
				if get_datetime(self.woocommerce_product.woocommerce_date_modified) > get_datetime(
					self.item.item.modified
				):
					self.update_item(self.woocommerce_product, self.item)
				if get_datetime(self.woocommerce_product.woocommerce_date_modified) < get_datetime(
					self.item.item.modified
				):
					self.update_woocommerce_product(self.woocommerce_product, self.item)

	def update_item(self, woocommerce_product: WooCommerceProduct, item: ERPNextItemToSync):
		"""
		Update the ERPNext Item with fields from it's corresponding WooCommerce Product
		"""
		if item.item.item_name != woocommerce_product.woocommerce_name:
			item.item.item_name = woocommerce_product.woocommerce_name
		self.set_item_fields()

		self.set_sync_hash()

	def update_woocommerce_product(
		self, wc_product: WooCommerceProduct, item: ERPNextItemToSync
	) -> None:
		"""
		Update the WooCommerce Product with fields from it's corresponding ERPNext Item
		"""
		wc_product_dirty = False

		# Update properties
		if wc_product.woocommerce_name != item.item.item_name:
			wc_product.woocommerce_name = item.item.item_name
			wc_product_dirty = True

		if self.set_product_fields(wc_product, item):
			wc_product_dirty = True

		if wc_product_dirty:
			wc_product.save()

		self.woocommerce_product = wc_product
		self.set_sync_hash()

	def create_woocommerce_product(self, item: ERPNextItemToSync) -> None:
		"""
		Create the WooCommerce Product with fields from it's corresponding ERPNext Item
		"""
		if (
			item.item_woocommerce_server.woocommerce_server
			and item.item_woocommerce_server.enabled
			and not item.item_woocommerce_server.woocommerce_id
		):
			# Create a new WooCommerce Product doc
			wc_product = frappe.get_doc({"doctype": "WooCommerce Product"})

			wc_product.type = "simple"

			# Handle variants
			if item.item.has_variants:
				wc_product.type = "variable"
				wc_product_attributes = []

				# Handle attributes
				for row in item.item.attributes:
					item_attribute = frappe.get_doc("Item Attribute", row.attribute)
					wc_product_attributes.append(
						{
							"name": row.attribute,
							"slug": row.attribute.lower().replace(" ", "_"),
							"visible": True,
							"variation": True,
							"options": [option.attribute_value for option in item_attribute.item_attribute_values],
						}
					)

				wc_product.attributes = json.dumps(wc_product_attributes)

			if item.item.variant_of:
				# Check if parent exists
				parent_item = frappe.get_doc("Item", item.item.variant_of)
				parent_item, parent_wc_product = run_item_sync(item_code=parent_item.item_code)
				wc_product.parent_id = parent_wc_product.woocommerce_id
				wc_product.type = "variation"

				# Handle attributes
				wc_product_attributes = [
					{
						"name": row.attribute,
						"slug": row.attribute.lower().replace(" ", "_"),
						"option": row.attribute_value,
					}
					for row in item.item.attributes
				]

				wc_product.attributes = json.dumps(wc_product_attributes)

			# Set properties
			wc_product.woocommerce_server = item.item_woocommerce_server.woocommerce_server
			wc_product.woocommerce_name = item.item.item_name
			wc_product.regular_price = get_item_price_rate(item) or "0"

			self.set_product_fields(wc_product, item)

			wc_product.insert()
			self.woocommerce_product = wc_product

			# Reload ERPNext Item
			item.item.reload()
			item.item_woocommerce_server.woocommerce_id = wc_product.woocommerce_id
			item.item.save()

			self.set_sync_hash()

	def create_item(self, wc_product: WooCommerceProduct) -> None:
		"""
		Create an ERPNext Item from the given WooCommerce Product
		"""
		wc_server = frappe.get_cached_doc("WooCommerce Server", wc_product.woocommerce_server)

		# Create Item
		item = frappe.new_doc("Item")

		# Handle variants' attributes
		if wc_product.type in ["variable", "variation"]:
			self.create_or_update_item_attributes(wc_product)
			wc_attributes = json.loads(wc_product.attributes)
			for wc_attribute in wc_attributes:
				row = item.append("attributes")
				row.attribute = wc_attribute["name"]
				if wc_product.type == "variation":
					row.attribute_value = wc_attribute["option"]

		# Handle variants
		if wc_product.type == "variable":
			item.has_variants = 1

		if wc_product.type == "variation":
			# Check if parent exists
			woocommerce_product_name = generate_woocommerce_record_name_from_domain_and_id(
				wc_product.woocommerce_server, wc_product.parent_id
			)
			parent_item, parent_wc_product = run_item_sync(
				woocommerce_product_name=woocommerce_product_name
			)
			item.variant_of = parent_item.item_code

		item.item_code = (
			wc_product.sku
			if wc_server.name_by == "Product SKU" and wc_product.sku
			else str(wc_product.woocommerce_id)
		)
		item.stock_uom = wc_server.uom or _("Nos")
		item.item_group = wc_server.item_group
		item.item_name = wc_product.woocommerce_name
		row = item.append("woocommerce_servers")
		row.woocommerce_id = wc_product.woocommerce_id
		row.woocommerce_server = wc_server.name
		item.flags.ignore_mandatory = True
		item.insert()

		self.item = ERPNextItemToSync(
			item=item,
			item_woocommerce_server_idx=next(
				iws.idx
				for iws in item.woocommerce_servers
				if iws.woocommerce_server == wc_product.woocommerce_server
			),
		)

		self.set_item_fields()

		self.set_sync_hash()

	def create_or_update_item_attributes(self, wc_product: WooCommerceProduct):
		"""
		Create or update an Item Attribute
		"""
		if wc_product.attributes:
			wc_attributes = json.loads(wc_product.attributes)
			for wc_attribute in wc_attributes:
				if frappe.db.exists("Item Attribute", wc_attribute["name"]):
					# Get existing Item Attribute
					item_attribute = frappe.get_doc("Item Attribute", wc_attribute["name"])
				else:
					# Create a Item Attribute
					item_attribute = frappe.get_doc(
						{"doctype": "Item Attribute", "attribute_name": wc_attribute["name"]}
					)

				# Get list of attribute options.
				# In variable WooCommerce Products, it's a list with key "options"
				# In a WooCommerce Product variant, it's a single value with key "option"
				options = (
					wc_attribute["options"] if wc_product.type == "variable" else [wc_attribute["option"]]
				)

				# If no attributes values exist, or attribute values exist already but are different, remove and update them
				if len(item_attribute.item_attribute_values) == 0 or (
					len(item_attribute.item_attribute_values) > 0
					and set(options) != set([val.attribute_value for val in item_attribute.item_attribute_values])
				):
					item_attribute.item_attribute_values = []
					for option in options:
						row = item_attribute.append("item_attribute_values")
						row.attribute_value = option
						row.abbr = option.replace(" ", "")

				item_attribute.flags.ignore_mandatory = True
				if not item_attribute.name:
					item_attribute.insert()
				else:
					item_attribute.save()

	def set_item_fields(self):
		"""
		If there exist any Field Mappings on `WooCommerce Server`, attempt to synchronise their values from
		WooCommerce to ERPNext
		"""
		if self.item and self.woocommerce_product:
			wc_server = frappe.get_cached_doc(
				"WooCommerce Server", self.woocommerce_product.woocommerce_server
			)
			if wc_server.item_field_map:
				for map in wc_server.item_field_map:
					erpnext_item_field_name = map.erpnext_field_name.split(" | ")
					woocommerce_product_field_value = self.woocommerce_product.get(map.woocommerce_field_name)

					frappe.db.set_value(
						"Item",
						self.item.item.name,
						erpnext_item_field_name[0],
						woocommerce_product_field_value,
						update_modified=False,
					)

	def set_product_fields(
		self, woocommerce_product: WooCommerceProduct, item: ERPNextItemToSync
	) -> bool:
		"""
		If there exist any Field Mappings on `WooCommerce Server`, attempt to synchronise their values from
		ERPNext to WooCommerce

		Returns true if woocommerce_product was changed
		"""
		if item and woocommerce_product:
			wc_server = frappe.get_cached_doc("WooCommerce Server", woocommerce_product.woocommerce_server)
			if wc_server.item_field_map:
				wc_product_dirty = False
				for map in wc_server.item_field_map:
					erpnext_item_field_name = map.erpnext_field_name.split(" | ")
					erpnext_item_field_value = getattr(item.item, erpnext_item_field_name[0])

					if erpnext_item_field_value != getattr(woocommerce_product, map.woocommerce_field_name):
						setattr(woocommerce_product, map.woocommerce_field_name, erpnext_item_field_value)
						wc_product_dirty = True

		return wc_product_dirty

	def set_sync_hash(self):
		"""
		Set the last sync hash value using db.set_value, as it does not call the ORM triggers
		and it does not update the modified timestamp (by using the update_modified parameter)
		"""
		frappe.db.set_value(
			"Item WooCommerce Server",
			self.item.item_woocommerce_server.name,
			"woocommerce_last_sync_hash",
			self.woocommerce_product.woocommerce_date_modified,
			update_modified=False,
		)


def get_list_of_wc_products(
	item: Optional[ERPNextItemToSync] = None, date_time_from: Optional[datetime] = None
) -> List[WooCommerceProduct]:
	"""
	Fetches a list of WooCommerce Products within a specified date range or linked with Items, using pagination.

	At least one of date_time_from, item parameters are required
	"""
	if not any([date_time_from, item]):
		raise ValueError("At least one of date_time_from or item parameters are required")

	wc_records_per_page_limit = 100
	page_length = wc_records_per_page_limit
	new_results = True
	start = 0
	filters = []
	wc_products = []
	servers = None

	# Build filters
	if date_time_from:
		filters.append(["WooCommerce Product", "date_modified", ">", date_time_from])
	if item:
		filters.append(["WooCommerce Product", "id", "=", item.item_woocommerce_server.woocommerce_id])
		servers = [item.item_woocommerce_server.woocommerce_server]

	while new_results:
		woocommerce_product = frappe.get_doc({"doctype": "WooCommerce Product"})
		new_results = woocommerce_product.get_list(
			args={
				"filters": filters,
				"page_lenth": page_length,
				"start": start,
				"servers": servers,
				"initialised": True,
			}
		)
		for wc_product in new_results:
			wc_products.append(wc_product)
		start += page_length

	return wc_products


def get_item_price_rate(item: ERPNextItemToSync):
	"""
	Get the Item Price if Item Price sync is enabled
	"""
	# Check if the Item Price sync is enabled
	wc_server = frappe.get_cached_doc(
		"WooCommerce Server", item.item_woocommerce_server.woocommerce_server
	)
	if wc_server.enable_price_list_sync:
		item_prices = frappe.get_all(
			"Item Price",
			filters={"item_code": item.item.item_name, "price_list": wc_server.price_list},
			fields=["price_list_rate", "valid_upto"],
		)
		return next(
			(
				price.price_list_rate
				for price in item_prices
				if not price.valid_upto or price.valid_upto > now()
			),
			None,
		)


def clear_sync_hash_and_run_item_sync(item_code: str):
	"""
	Clear the last sync hash value using db.set_value, as it does not call the ORM triggers
	and it does not update the modified timestamp (by using the update_modified parameter)
	"""

	iws = frappe.qb.DocType("Item WooCommerce Server")

	iwss = (
		frappe.qb.from_(iws).where(iws.enabled == 1).where(iws.parent == item_code).select(iws.name)
	).run(as_dict=True)

	for iws in iwss:
		frappe.db.set_value(
			"Item WooCommerce Server",
			iws.name,
			"woocommerce_last_sync_hash",
			None,
			update_modified=False,
		)

	run_item_sync(item_code=item_code, enqueue=True)
