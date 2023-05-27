from unittest.mock import MagicMock, Mock, patch, call

import frappe
from frappe.tests.utils import FrappeTestCase

from woocommerce_fusion.tasks.stock_update import \
	update_stock_levels_on_woocommerce_site

@patch("woocommerce_fusion.tasks.stock_update.frappe")
@patch("woocommerce_fusion.tasks.stock_update.API", autospec=True)
class TestWooCommerceOrder(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()  # important to call super() methods when extending TestCase.

	def test_update_stock_levels_on_woocommerce_site(self, mock_wc_api, mock_frappe):
		# Set up a dummy item set to sync to two different WC sites
		some_item = frappe._dict(
			woocommerce_servers=[
				frappe._dict(
					woocommerce_id=1,
					woocommerce_site="woo1.example.com"
				),
				frappe._dict(
					woocommerce_id=2,
					woocommerce_site="woo2.example.com"
				)
			]
		)
		mock_frappe.get_doc.return_value = some_item

		# Set up a dummy bin list with stock in two Warehouses
		bin_list = [
			frappe._dict(
				warehouse="Warehouse A",
				actual_qty=5
			),
			frappe._dict(
				warehouse="Warehouse B",
				actual_qty=10
			)
		]
		mock_frappe.get_list.return_value = bin_list

		# Set up a dummy settings doc with two different WC servers
		wc_additional_settings = frappe._dict(
			servers=[
				frappe._dict(
					woocommerce_server_url="https://woo1.example.com/",
					enable_sync=1
				),
				frappe._dict(
					woocommerce_server_url="https://woo2.example.com/",
					enable_sync=1
				)
			],
			warehouses=[
				frappe._dict(
					warehouse="Warehouse A",
					woocommerce_inventory_name="Storage A"
				),
				frappe._dict(
					warehouse="Warehouse B",
					woocommerce_inventory_name="Storage B"
				)
			]
		)
		mock_frappe.get_single.return_value = wc_additional_settings

		# Mock out calls to WooCommerce API's
		mock_product_inventories = [
			{
				"id": 123,
				"name": "Storage A"
			},
			{
				"id": 345,
				"name": "Storage B"
			}
		]
		mock_get_response = Mock()
		mock_get_response.status_code = 200

		to_json = Mock()
		to_json.return_value = mock_product_inventories
		mock_get_response.json = to_json

		mock_post_response = Mock()
		mock_post_response.status_code = 200

		mock_api_instance = MagicMock()
		mock_api_instance.get.return_value = mock_get_response
		mock_api_instance.post.return_value = mock_post_response
		mock_wc_api.return_value = mock_api_instance

		# Call function under test
		update_stock_levels_on_woocommerce_site("some_item_code")

		# Assert that the correct API's were called
		actual_get_urls = [call.kwargs['url'] for call in mock_wc_api.call_args_list]
		expected_get_urls = ["https://woo1.example.com/", "https://woo2.example.com/"]
		self.assertEqual(actual_get_urls, expected_get_urls)
		
		# Assert that the inventories get calls were made with the correct arguments
		self.assertEqual(mock_api_instance.get.call_count, 2)
		expected_get_calls = [call('products/1/inventories'), call('products/2/inventories')]
		self.assertEqual(mock_api_instance.get.call_args_list, expected_get_calls)
		
		# Assert that the inventories post calls were made with the correct arguments
		self.assertEqual(mock_api_instance.post.call_count, 2)
		actual_post_endpoints = [call.kwargs['endpoint'] for call in mock_api_instance.post.call_args_list]
		actual_post_data = [call.kwargs['data'] for call in mock_api_instance.post.call_args_list]
		
		expected_post_endpoints = ['products/1/inventories/batch', 'products/2/inventories/batch']
		expected_data = {
			'update': [{'id': 123, 'meta_data': {'stock_quantity': 5}},
						{'id': 345, 'meta_data': {'stock_quantity': 10}}]
		}
		expected_post_data  = [expected_data for x in range(2)]
		self.assertEqual(actual_post_endpoints, expected_post_endpoints)
		self.assertEqual(actual_post_data, expected_post_data)
