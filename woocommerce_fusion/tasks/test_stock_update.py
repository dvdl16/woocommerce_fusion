from unittest.mock import MagicMock, Mock, call, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from woocommerce_fusion.tasks.stock_update import update_stock_levels_on_woocommerce_site


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
				frappe._dict(woocommerce_id=1, woocommerce_site="woo1.example.com"),
				frappe._dict(woocommerce_id=2, woocommerce_site="woo2.example.com"),
			]
		)
		mock_frappe.get_doc.return_value = some_item

		# Set up a dummy bin list with stock in two Warehouses
		bin_list = [
			frappe._dict(warehouse="Warehouse A", actual_qty=5),
			frappe._dict(warehouse="Warehouse B", actual_qty=10),
		]
		mock_frappe.get_list.return_value = bin_list

		# Set up a dummy settings doc with two different WC servers
		wc_additional_settings = frappe._dict(
			servers=[
				frappe._dict(woocommerce_server_url="https://woo1.example.com/", enable_sync=1),
				frappe._dict(woocommerce_server_url="https://woo2.example.com/", enable_sync=1),
			]
		)
		mock_frappe.get_single.return_value = wc_additional_settings

		# Mock out calls to WooCommerce API's
		mock_put_response = Mock()
		mock_put_response.status_code = 200

		mock_api_instance = MagicMock()
		mock_api_instance.put.return_value = mock_put_response
		mock_wc_api.return_value = mock_api_instance

		# Call function under test
		update_stock_levels_on_woocommerce_site("some_item_code")

		# Assert that the inventories put calls were made with the correct arguments
		self.assertEqual(mock_api_instance.put.call_count, 2)
		actual_put_endpoints = [call.kwargs["endpoint"] for call in mock_api_instance.put.call_args_list]
		actual_put_data = [call.kwargs["data"] for call in mock_api_instance.put.call_args_list]

		expected_put_endpoints = ["products/1", "products/2"]
		expected_data = {"stock_quantity": 15}
		expected_put_data = [expected_data for x in range(2)]
		self.assertEqual(actual_put_endpoints, expected_put_endpoints)
		self.assertEqual(actual_put_data, expected_put_data)
