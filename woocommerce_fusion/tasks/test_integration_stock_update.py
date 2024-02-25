import math
from urllib.parse import urlparse

import frappe
from erpnext import get_default_company
from erpnext.stock.doctype.item.test_item import create_item

from woocommerce_fusion.tasks.stock_update import update_stock_levels_on_woocommerce_site
from woocommerce_fusion.tasks.test_integration_helpers import (
	TestIntegrationWooCommerce,
	get_woocommerce_server,
)


class TestIntegrationWooCommerceStockSync(TestIntegrationWooCommerce):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()  # important to call super() methods when extending TestCase.

	def test_stock_sync_when_synchronising_with_woocommerce(self):
		"""
		Test that the Stock Synchornisation method posts the correct stock level to a WooCommerce website.
		"""
		# Create a new product in WooCommerce, set opening stock to 1
		wc_product_id = self.post_woocommerce_product(product_name="ITEM001", opening_stock=1)

		# Create the same product in ERPNext (with opening stock of 5, not 1) and link it
		item = create_item(
			"ITEM001", valuation_rate=10, warehouse=None, company=get_default_company(), opening_stock=5
		)
		item.woocommerce_servers = []
		row = item.append("woocommerce_servers")
		row.woocommerce_id = wc_product_id
		row.woocommerce_server = get_woocommerce_server(self.wc_url).name
		item.save()

		# Run synchronisation
		stock_update_result = update_stock_levels_on_woocommerce_site(item_code=item.name)

		# Expect successful update
		self.assertEqual(stock_update_result, True)

		# Expect correct stock level of 5 in WooCommerce
		wc_stock_level = self.get_woocommerce_product_stock_level(product_id=wc_product_id)
		self.assertEqual(wc_stock_level, 5)

	# def test_stock_sync_with_decimal_when_synchronising_with_woocommerce(self):
	# 	"""
	# 	Test that the Stock Synchornisation method posts the correct stock level to a WooCommerce website
	# 	while handling decimals.
	# 	"""
	# 	# Create a new product in WooCommerce, set opening stock to 1
	# 	wc_product_id = self.post_woocommerce_product(product_name="ITEM002", opening_stock=1)

	# 	# Create the same product in ERPNext (with opening stock of 6.9, not 1) and link it
	# 	item = create_item(
	# 		"ITEM002",
	# 		valuation_rate=10,
	# 		warehouse=None,
	# 		company=get_default_company(),
	# 		stock_uom="Kg",
	# 		opening_stock=6.9,
	# 	)
	# 	row = item.append("woocommerce_servers")
	# 	row.woocommerce_id = wc_product_id
	# 	row.woocommerce_server = get_woocommerce_server(self.wc_url).name
	# 	item.save()

	# 	# Run synchronisation
	# 	stock_update_result = update_stock_levels_on_woocommerce_site(item_code=item.name)

	# 	# Expect successful update
	# 	self.assertEqual(stock_update_result, True)

	# 	# Expect correct stock level of 6.9 rounded down in WooCommerce (WooCommerce API doesn't accept float values)
	# 	wc_stock_level = self.get_woocommerce_product_stock_level(product_id=wc_product_id)
	# 	self.assertEqual(wc_stock_level, math.floor(6.9))
