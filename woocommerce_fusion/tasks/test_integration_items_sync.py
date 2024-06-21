from unittest.mock import patch

import frappe
from erpnext.stock.doctype.item.test_item import create_item
from frappe.utils.data import cstr

from woocommerce_fusion.tasks.sync_items import run_item_sync
from woocommerce_fusion.tasks.test_integration_helpers import TestIntegrationWooCommerce
from woocommerce_fusion.woocommerce.woocommerce_api import (
	generate_woocommerce_record_name_from_domain_and_id,
)


@patch("woocommerce_fusion.tasks.sync_items.frappe.log_error")
class TestIntegrationWooCommerceItemsSync(TestIntegrationWooCommerce):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()  # important to call super() methods when extending TestCase.

	def test_sync_create_new_item_when_synchronising_with_woocommerce(self, mock_log_error):
		"""
		Test that the Item Synchronisation method creates new Items when there are new
		WooCommerce products.
		"""
		# Create a new product in WooCommerce
		wc_product_id = self.post_woocommerce_product(product_name="SOME_ITEM")

		# Run synchronisation
		woocommerce_product_name = generate_woocommerce_record_name_from_domain_and_id(
			self.wc_server.name, wc_product_id
		)
		run_item_sync(woocommerce_product_name=woocommerce_product_name)

		# Expect no errors logged
		mock_log_error.assert_not_called()

		# Expect newly created Item in ERPNext
		items = get_items_for_wc_product(wc_product_id, self.wc_server.name)
		self.assertEqual(len(items), 1)
		item = items[0]
		self.assertIsNotNone(item)

		# Expect correct item code and name in item
		self.assertEqual(item.item_code, str(wc_product_id))
		self.assertEqual(item.item_name, "SOME_ITEM")

	def test_sync_create_new_template_item_when_synchronising_with_woocommerce(self, mock_log_error):
		"""
		Test that the Item Synchronisation method creates new Template Item from a WooCommerce Product with Variations
		"""
		# Create a new product in WooCommerce
		wc_product_id = self.post_woocommerce_product(
			product_name="T-SHIRT", type="variable", attributes=["Material Type", "Volume"]
		)

		# Run synchronisation
		woocommerce_product_name = generate_woocommerce_record_name_from_domain_and_id(
			self.wc_server.name, wc_product_id
		)
		run_item_sync(woocommerce_product_name=woocommerce_product_name)

		# Expect no errors logged
		mock_log_error.assert_not_called()

		# Expect newly created Item in ERPNext
		items = get_items_for_wc_product(wc_product_id, self.wc_server.name)
		self.assertEqual(len(items), 1)
		item = items[0]
		self.assertIsNotNone(item)

		# Expect template item in ERPNext
		self.assertEqual(item.has_variants, 1)

		# Expect same attributes
		self.assertEqual(len(item.attributes), 2)
		self.assertEqual(item.attributes[0].attribute, "Material Type")
		self.assertEqual(item.attributes[1].attribute, "Volume")

	def test_sync_create_new_variant_item_when_synchronising_with_woocommerce(self, mock_log_error):
		"""
		Test that the Item Synchronisation method creates new Item Variant from a
		WooCommerce Product Variant
		"""
		# Create a new product in WooCommerce
		wc_product_id = self.post_woocommerce_product(
			product_name="T-SHIRT", type="variation", attributes=["Material Type"]
		)

		# Run synchronisation
		woocommerce_product_name = generate_woocommerce_record_name_from_domain_and_id(
			self.wc_server.name, wc_product_id
		)
		run_item_sync(woocommerce_product_name=woocommerce_product_name)

		# Expect no errors logged
		mock_log_error.assert_not_called()

		# Expect newly created Item in ERPNext
		items = get_items_for_wc_product(wc_product_id, self.wc_server.name)
		self.assertEqual(len(items), 1)
		item = items[0]
		self.assertIsNotNone(item)

		# Expect variant item in ERPNext
		self.assertIsNotNone(item.variant_of)
		self.assertEqual(item.has_variants, 0)

		# Expect same attribute
		self.assertEqual(len(item.attributes), 1)
		self.assertEqual(item.attributes[0].attribute, "Material Type")
		self.assertIsNotNone(item.attributes[0].attribute_value)

	def test_sync_create_new_wc_product_when_synchronising_with_woocommerce(self, mock_log_error):
		"""
		Test that the Item Synchronisation method creates a new WooCommerce product when there are new
		Items.
		"""
		# Create a new item in ERPNext and set a WooCommerce server but not a product ID
		item = create_item("ITEM101", valuation_rate=10)
		row = item.append("woocommerce_servers")
		row.woocommerce_server = self.wc_server.name
		item.save()

		# Run synchronisation
		run_item_sync(item_code=item.name)

		# Expect no errors logged
		mock_log_error.assert_not_called()

		# Get the updated item
		item.reload()

		# Expect a row in WooCommerce Servers child table and that WooCommerceID is set
		self.assertEqual(len(item.woocommerce_servers), 1)
		self.assertIsNotNone(item.woocommerce_servers[0].woocommerce_id)

		# Expect newly created WooCommerce Product
		wc_product = self.get_woocommerce_product(product_id=item.woocommerce_servers[0].woocommerce_id)

		# Expect correct item name in item
		self.assertEqual(wc_product["name"], item.item_name)

	def test_sync_create_new_variable_wc_product_when_synchronising_with_woocommerce(
		self, mock_log_error
	):
		"""
		Test that the Item Synchronisation method creates a new Variable WooCommerce product
		when there is a new Template Item in ERPNext
		"""
		# Create a new item in ERPNext and set a WooCommerce server but not a product ID
		item = create_item("ITEM100", valuation_rate=10)
		row = item.append("woocommerce_servers")
		row.woocommerce_server = self.wc_server.name

		# Make this item a Template item with Attributes
		item.has_variants = 1
		for attr in ["Material Type", "Volume"]:
			create_item_attribute(attr)
			row = item.append("attributes")
			row.attribute = attr

		item.save()

		# Run synchronisation
		run_item_sync(item_code=item.name)

		# Expect no errors logged
		mock_log_error.assert_not_called()

		# Get the updated item
		item.reload()

		# Expect newly created WooCommerce Product
		wc_product = self.get_woocommerce_product(product_id=item.woocommerce_servers[0].woocommerce_id)
		self.assertEqual(wc_product["type"], "variable")

		# Expect attributes to be set
		self.assertEqual(len(wc_product["attributes"]), 2)
		self.assertEqual(wc_product["attributes"][0]["name"], "Material Type")
		self.assertEqual(wc_product["attributes"][0]["variation"], True)
		self.assertEqual(wc_product["attributes"][1]["name"], "Volume")
		self.assertEqual(wc_product["attributes"][1]["variation"], True)

	def test_sync_create_new_wc_product_variant_when_synchronising_with_woocommerce(
		self, mock_log_error
	):
		"""
		Test that the Item Synchronisation method creates a new WooCommerce product variant
		when there is a new Item Variant in ERPNext
		"""
		# Create a new parent item in ERPNext and set a WooCommerce server but not a product ID
		parent_item = create_item("ITEM200-Parent", valuation_rate=10)
		row = parent_item.append("woocommerce_servers")
		row.woocommerce_server = self.wc_server.name
		parent_item.has_variants = 1
		for attr in ["Material Type", "Volume"]:
			create_item_attribute(attr)
			row = parent_item.append("attributes")
			row.attribute = attr
		parent_item.save()

		# Create a new item in ERPNext and set a WooCommerce server but not a product ID
		# Make this item a Variant Item with Attributes
		item = create_variant_item(
			"ITEM200-Variant",
			valuation_rate=10,
			variant_of=parent_item.name,
			attributes=[("Material Type", "Option 2")],
		)
		row = item.append("woocommerce_servers")
		row.woocommerce_server = self.wc_server.name
		item.save()

		# Run synchronisation
		run_item_sync(item_code=item.name)

		# Expect no errors logged
		mock_log_error.assert_not_called()

		# Get the updated items
		parent_item.reload()
		item.reload()

		# Expect newly created WooCommerce Product
		wc_product = self.get_woocommerce_product(
			product_id=item.woocommerce_servers[0].woocommerce_id,
			parent_id=parent_item.woocommerce_servers[0].woocommerce_id,
		)
		self.assertIn("id", wc_product)
		self.assertIsNotNone(wc_product["id"])

		# Expect attributes to be set
		self.assertEqual(len(wc_product["attributes"]), 1)
		self.assertEqual(wc_product["attributes"][0]["name"], "Material Type")
		self.assertEqual(wc_product["attributes"][0]["option"], "Option 2")


def get_items_for_wc_product(woocommerce_id: str, woocommerce_server: str):
	"""
	Get ERPNext Item for a given WooCommerce Product and Server
	"""
	iws = frappe.qb.DocType("Item WooCommerce Server")
	itm = frappe.qb.DocType("Item")
	item_codes = (
		frappe.qb.from_(iws)
		.join(itm)
		.on(iws.parent == itm.name)
		.where(
			(iws.woocommerce_id == cstr(woocommerce_id))
			& (iws.woocommerce_server == woocommerce_server)
			& (itm.disabled == 0)
		)
		.select(iws.parent)
		.limit(1)
	).run(as_dict=True)

	return [frappe.get_doc("Item", item_code.parent) for item_code in item_codes]


def create_item_attribute(attribute_name: str):
	"""
	Create an Item Attribute
	"""
	if not frappe.db.exists("Item Attribute", attribute_name):
		# Create a Item Attribute
		item_attribute = frappe.get_doc({"doctype": "Item Attribute", "attribute_name": attribute_name})
		options = ["Option 1", "Option 2", "Option 3"]
		for option in options:
			row = item_attribute.append("item_attribute_values")
			row.attribute_value = option
			row.abbr = option.replace(" ", "")

		item_attribute.flags.ignore_mandatory = True
		item_attribute.insert()


def create_variant_item(
	item_code,
	is_stock_item=1,
	valuation_rate=0,
	stock_uom="Nos",
	warehouse="_Test Warehouse - _TC",
	is_customer_provided_item=None,
	customer=None,
	is_purchase_item=None,
	opening_stock=0,
	is_fixed_asset=0,
	asset_category=None,
	company="_Test Company",
	variant_of=None,
	attributes=None,
):
	if not frappe.db.exists("Item", item_code):
		item = frappe.new_doc("Item")
		item.item_code = item_code
		item.item_name = item_code
		item.description = item_code
		item.item_group = "All Item Groups"
		item.stock_uom = stock_uom
		item.is_stock_item = is_stock_item
		item.is_fixed_asset = is_fixed_asset
		item.asset_category = asset_category
		item.opening_stock = opening_stock
		item.valuation_rate = valuation_rate
		item.is_purchase_item = is_purchase_item
		item.is_customer_provided_item = is_customer_provided_item
		item.customer = customer or ""
		item.append("item_defaults", {"default_warehouse": warehouse, "company": company})
		item.variant_of = variant_of
		if attributes:
			for attribute, attribute_value in attributes:
				row = item.append("attributes")
				row.attribute = attribute
				row.attribute_value = attribute_value
		item.save()
	else:
		item = frappe.get_doc("Item", item_code)
	return item
