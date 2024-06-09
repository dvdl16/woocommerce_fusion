from unittest.mock import patch

import frappe
from erpnext.stock.doctype.item.test_item import create_item

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
		items = frappe.get_all(
			"Item", filters={"woocommerce_id": wc_product_id}, fields=["item_code", "item_name"]
		)
		self.assertEqual(len(items), 1)
		item = items[0]
		self.assertIsNotNone(item)

		# Expect correct item code and name in item
		self.assertEqual(item.item_code, str(wc_product_id))
		self.assertEqual(item.item_name, "SOME_ITEM")

	# def test_sync_create_new_template_item_when_synchronising_with_woocommerce(self, mock_log_error):
	# 	"""
	# 	Test that the Item Synchronisation method creates new Template Item from a WooCommerce Product with Variations
	# 	"""
	# 	# Create a new product in WooCommerce
	# 	wc_product_id = self.post_woocommerce_product(product_name="T-SHIRT", is_variable=True)

	# 	# Run synchronisation
	# 	woocommerce_product_name = generate_woocommerce_record_name_from_domain_and_id(self.wc_server.name, wc_product_id)
	# 	run_item_sync(woocommerce_product_name=woocommerce_product_name)

	# 	# Expect no errors logged
	# 	mock_log_error.assert_not_called()

	# 	# Expect newly created Item in ERPNext
	# 	items = frappe.get_all("Item", filters={"woocommerce_id": wc_product_id}, fields=["has_variants"])
	# 	self.assertEqual(len(items), 1)
	# 	item = items[0]
	# 	self.assertIsNotNone(item)

	# 	# Expect template item in ERPNext
	# 	self.assertEqual(item.has_variants, 1)

	def test_sync_create_new_wc_product_when_synchronising_with_woocommerce(self, mock_log_error):
		"""
		Test that the Item Synchronisation method creates a new WooCommerce product when there are new
		Iems.
		"""
		# Create a new item in ERPNext and set a WooCommerce server but not a product ID
		item = create_item("ITEM100", valuation_rate=10)
		item = frappe.get_doc("Item", "ITEM100")
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
