# Copyright (c) 2023, Dirk van der Laarse and Contributors
# See license.txt

from unittest.mock import Mock, patch
from copy import deepcopy
import json
from urllib.parse import urlparse

import frappe
from frappe.tests.utils import FrappeTestCase

from woocommerce_fusion.woocommerce.doctype.woocommerce_order.woocommerce_order import WC_ORDER_DELIMITER, WooCommerceAPI, WooCommerceOrder


@patch('woocommerce_fusion.woocommerce.doctype.woocommerce_order.woocommerce_order._init_api')
class TestWooCommerceOrder(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()  # important to call super() methods when extending TestCase.

	def test_get_list_returns_orders_with_name_attribute(self, mock_init_api):
		"""
		Test that get_list returns a list of Orders, each with a 'name' attribute
		"""
		nr_of_orders = 3
		woocommerce_server_url = "site1.example.com"
		
		# Create mock API object
		mock_api_list = [
			WooCommerceAPI(
				api=Mock(),
				woocommerce_server_url=woocommerce_server_url,
				wc_plugin_advanced_shipment_tracking=1
			)
		]

		mock_init_api.return_value = mock_api_list

		# Define the mock response from the get method
		mock_get_response = Mock()
		mock_get_response.status_code = 200
		mock_get_response.json.return_value = wc_response_for_list_of_orders(nr_of_orders)

		# Set the mock response to be returned when get is called on the mock API
		mock_api_list[0].api.get.return_value = mock_get_response

		# Call the method to be tested
		woocommerce_order = frappe.get_doc({
			'doctype': 'WooCommerce Order'
		})
		orders = woocommerce_order.get_list({})

		# Check that the API was initialised
		mock_init_api.assert_called_once()

		# Check that the API was called
		mock_api_list[0].api.get.assert_called_once()

		# Verify that the orders endpoint is called
		self.assertEqual(mock_api_list[0].api.get.call_args.args[0], 'orders')

		# Verify that the list of orders have been retrieved
		self.assertEqual(len(orders), nr_of_orders)
		
		# Verify that a 'name' attribute has been created with value of '[domain]~[id]'
		for order in orders:
			self.assertTrue('name' in order)
			expected_name = urlparse(woocommerce_server_url).netloc + WC_ORDER_DELIMITER + str(order['id'])
			self.assertEqual(order['name'], expected_name)


	# @patch.object(WooCommerceOrder, 'get_additional_order_attributes')
	def test_load_from_db_initialises_doctype_with_all_values(self, mock_init_api):
		"""
		Test that load_from_db returns an Order
		"""
		order_id = 1
		woocommerce_server_url = "site1.example.com"

		# Setup mock API
		mock_api_list = [
			WooCommerceAPI(
				api=Mock(),
				woocommerce_server_url=woocommerce_server_url,
				wc_plugin_advanced_shipment_tracking=1
			)
		]
		mock_init_api.return_value = mock_api_list

		# Define the mock response from the get method
		mock_get_response = Mock()
		mock_get_response.json.return_value = deepcopy(dummy_wc_order)

		# Set the mock response to be returned when get is called on the mock API
		mock_api_list[0].api.get.return_value = mock_get_response

		# Patch out the __init__ method
		with patch.object(WooCommerceOrder, "__init__", return_value=None) as mock_init:

			# Patch out the call_super_init method
			with patch.object(WooCommerceOrder, "call_super_init") as mocked_super_call:

				# Patch out the get_additional_order_attributes
				with patch.object(WooCommerceOrder, "get_additional_order_attributes") as mock_get_additional_order_attributes:

					# Set the mock_get_additional_order_attributes method to return its argument
					mock_get_additional_order_attributes.side_effect = lambda x: x

					# Instantiate the class
					woocommerce_order = WooCommerceOrder()
					woocommerce_order.doctype = "WooCommerce Order"
					woocommerce_order.name = woocommerce_server_url + WC_ORDER_DELIMITER + str(order_id)

					# Call load_from_db
					woocommerce_order.load_from_db()

					# Check that super's __init__ was called
					mocked_super_call.assert_called_once()

					# Check that all order fields are valid
					for key, value in mocked_super_call.call_args.args[0].items():
						# Test that Lists and Dicts are in JSON format, except for meta fieds
						meta_data_fields = ['modified', 'woocommerce_server_url']
						if key not in meta_data_fields:
							if isinstance(dummy_wc_order[key], dict) or isinstance(dummy_wc_order[key], list):
								self.assertEqual(json.loads(value), dummy_wc_order[key])
							else:
								self.assertEqual(value, dummy_wc_order[key])
	
		# Check that the API was initialised
		mock_init_api.assert_called_once()

		# Check that the API was called
		mock_api_list[0].api.get.assert_called_once()

		# Verify that the orders endpoint is called
		self.assertEqual(mock_api_list[0].api.get.call_args.args[0], f'orders/{order_id}')

	def test_db_insert_makes_post_call(self, mock_init_api):
		"""
		Test that db_insert makes a POST call to the WooCommerce API
		"""
		# Setup mock API
		mock_api_list = [
			WooCommerceAPI(
				api=Mock(),
				woocommerce_server_url="site1.example.com",
				wc_plugin_advanced_shipment_tracking=1
			)
		]
		mock_init_api.return_value = mock_api_list

		# Define the mock response from the post method
		mock_post_response = Mock()
		mock_post_response.status_code = 201

		# Set the mock response to be returned when POST is called on the mock API
		mock_api_list[0].api.post.return_value = mock_post_response

		# Prepare the mock order data by dumping lists and dicts to json
		mock_order_data = deepcopy(dummy_wc_order)
		for key, value in mock_order_data.items():
			if isinstance(mock_order_data[key], dict) or isinstance(mock_order_data[key], list):
				mock_order_data[key] = json.dumps(dummy_wc_order[key])

		# Call db_insert
		woocommerce_order = frappe.get_doc({
			'doctype': 'WooCommerce Order'
		})
		woocommerce_order.customer_note = "Hello World"
		woocommerce_order.woocommerce_server_url="site1.example.com"
		woocommerce_order.db_insert()

		# Check that the API was initialised
		mock_init_api.assert_called_once()

		# Check that the API was called
		mock_api_list[0].api.post.assert_called_once()

		# Verify that the orders endpoint is called
		self.assertEqual(mock_api_list[0].api.post.call_args.args[0], 'orders')

		# Verify that an attribute is passed to the API
		self.assertTrue('customer_note' in mock_api_list[0].api.post.call_args.kwargs['data'])
		self.assertEqual(mock_api_list[0].api.post.call_args.kwargs['data']['customer_note'], "Hello World")

	def test_db_insert_with_failed_post_call_throws_error(self, mock_init_api):
		"""
		Test that db_insert with a failed POST call throws an error
		"""
		# Setup mock API
		mock_api_list = [
			WooCommerceAPI(
				api=Mock(),
				woocommerce_server_url="site1.example.com",
				wc_plugin_advanced_shipment_tracking=1
			)
		]
		mock_init_api.return_value = mock_api_list

		# Define the mock response from the post method
		mock_post_response = Mock()
		mock_post_response.status_code = 400

		# Set the mock response to be returned when POST is called on the mock API
		mock_api_list[0].api.post.return_value = mock_post_response

		# Prepare the mock order data by dumping lists and dicts to json
		mock_order_data = deepcopy(dummy_wc_order)
		for key, value in mock_order_data.items():
			if isinstance(mock_order_data[key], dict) or isinstance(mock_order_data[key], list):
				mock_order_data[key] = json.dumps(dummy_wc_order[key])

		# Call db_insert
		woocommerce_order = frappe.get_doc({
			'doctype': 'WooCommerce Order'
		})
		woocommerce_order.woocommerce_server_url="site1.example.com"
		
		# Verify that an Exception is thrown
		with self.assertRaises(Exception) as context:
			woocommerce_order.db_insert()

		# Verify that the Exception is a Validation Error
		self.assertEqual('ValidationError', context.exception.__class__.__name__)

	@patch('woocommerce_fusion.woocommerce.doctype.woocommerce_order.woocommerce_order.WooCommerceOrder.update_shipment_tracking')
	def test_db_update_makes_put_call(self, mock_update_shipment_tracking, mock_init_api):
		"""
		Test that db_update makes a PUT call to the WooCommerce API
		"""
		order_id = 1
		woocommerce_server_url = "site1.example.com"

		# Setup mock API
		mock_api_list = [
			WooCommerceAPI(
				api=Mock(),
				woocommerce_server_url=woocommerce_server_url,
				wc_plugin_advanced_shipment_tracking=1
			)
		]
		mock_init_api.return_value = mock_api_list

		# Define the mock response from the put method
		mock_put_response = Mock()
		mock_put_response.status_code = 200

		# Set the mock response to be returned when PUT is called on the mock API
		mock_api_list[0].api.put.return_value = mock_put_response

		# Prepare the mock order data by dumping lists and dicts to json
		mock_order_data = deepcopy(dummy_wc_order)
		for key, value in mock_order_data.items():
			if isinstance(mock_order_data[key], dict) or isinstance(mock_order_data[key], list):
				mock_order_data[key] = json.dumps(dummy_wc_order[key])

		# Call db_update
		woocommerce_order = frappe.get_doc({
			'doctype': 'WooCommerce Order'
		})
		woocommerce_order.name = woocommerce_server_url + WC_ORDER_DELIMITER + str(order_id)
		woocommerce_order.customer_note = "Hello World"
		woocommerce_order.db_update()

		# Check that the API was initialised
		mock_init_api.assert_called_once()

		# Check that the API was called
		mock_api_list[0].api.put.assert_called_once()

		# Verify that the orders endpoint is called
		self.assertEqual(mock_api_list[0].api.put.call_args.args[0], f'orders/{order_id}')

		# Verify that an attribute is passed to the API
		self.assertTrue('customer_note' in mock_api_list[0].api.put.call_args.kwargs['data'])
		self.assertEqual(mock_api_list[0].api.put.call_args.kwargs['data']['customer_note'], "Hello World")


	def test_get_additional_order_attributes_makes_api_get(self, mock_init_api):
		"""
		Test that the get_additional_order_attributes method makes an API call
		"""
		order_id = 1
		woocommerce_server_url = "site1.example.com"
		# Setup mock API
		mock_api_list = [
			WooCommerceAPI(
				api=Mock(),
				woocommerce_server_url=woocommerce_server_url,
				wc_plugin_advanced_shipment_tracking=1
			)
		]
		mock_init_api.return_value = mock_api_list

		# Define the mock response from the get method
		mock_get_response = Mock()
		mock_get_response.json.return_value = None

		# Set the mock response to be returned when get is called on the mock API
		mock_api_list[0].api.get.return_value = mock_get_response

		# Patch out the __init__ method and set the required fields
		with patch.object(WooCommerceOrder, "__init__", return_value=None) as mock_init:
			woocommerce_order = WooCommerceOrder()
			woocommerce_order.name = woocommerce_server_url + WC_ORDER_DELIMITER + str(order_id)
			woocommerce_order.current_wc_api = mock_api_list[0]
			woocommerce_order.get_additional_order_attributes({})

		# Check that the API was called
		mock_api_list[0].api.get.assert_called_once()

		# Verify that the shipment-trackings endpoint is called
		self.assertEqual(mock_api_list[0].api.get.call_args.args[0], f'orders/{order_id}/shipment-trackings')


	def test_update_shipment_tracking_makes_api_post_when_shipment_trackings_changes(self, mock_init_api):
		"""
		Test that the update_shipment_tracking method makes an API POST call
		"""
		order_id = 1
		woocommerce_server_url = "site1.example.com"
		# Setup mock API
		mock_api_list = [
			WooCommerceAPI(
				api=Mock(),
				woocommerce_server_url=woocommerce_server_url,
				wc_plugin_advanced_shipment_tracking=1
			)
		]
		mock_init_api.return_value = mock_api_list

		# Define the mock response from the post method
		mock_post_response = Mock()
		mock_post_response.status_code = 201

		# Set the mock response to be returned when post is called on the mock API
		mock_api_list[0].api.post.return_value = mock_post_response

		# Patch out the __init__ method and set the required fields
		with patch.object(WooCommerceOrder, "__init__", return_value=None) as mock_init:
			woocommerce_order = WooCommerceOrder()
			woocommerce_order.init_api()
			woocommerce_order.name = woocommerce_server_url + WC_ORDER_DELIMITER + str(order_id)
			woocommerce_order.shipment_trackings = json.dumps([{'foo': 'bar'}])
			woocommerce_order._doc_before_save = frappe._dict({'shipment_trackings': json.dumps([{'foo': 'baz'}])})
			woocommerce_order.update_shipment_tracking()

		# Check that the API was called
		mock_api_list[0].api.post.assert_called_once()

		# Verify that the shipment-trackings endpoint is called
		self.assertEqual(mock_api_list[0].api.post.call_args.args[0], f'orders/{order_id}/shipment-trackings/')


	def test_update_shipment_tracking_does_not_make_api_post_when_shipment_trackings_is_unchanged(self, mock_init_api):
		"""
		Test that the update_shipment_tracking method does not make an API POST call when
		shipment_trackings is unchanged
		"""
		order_id = 1
		woocommerce_server_url = "site1.example.com"
		# Setup mock API
		mock_api_list = [
			WooCommerceAPI(
				api=Mock(),
				woocommerce_server_url=woocommerce_server_url,
				wc_plugin_advanced_shipment_tracking=1
			)
		]
		mock_init_api.return_value = mock_api_list

		# Define the mock response from the post method
		mock_post_response = Mock()
		mock_post_response.status_code = 201

		# Set the mock response to be returned when post is called on the mock API
		mock_api_list[0].api.post.return_value = mock_post_response

		# Patch out the __init__ method and set the required fields
		with patch.object(WooCommerceOrder, "__init__", return_value=None) as mock_init:
			woocommerce_order = WooCommerceOrder()
			woocommerce_order.init_api()
			woocommerce_order.name = woocommerce_server_url + WC_ORDER_DELIMITER + str(order_id)
			woocommerce_order.shipment_trackings = json.dumps([{'foo': 'bar'}])
			woocommerce_order._doc_before_save = frappe._dict({'shipment_trackings': json.dumps([{'foo': 'bar'}])})
			woocommerce_order.update_shipment_tracking()

		# Check that the API was not called
		mock_api_list[0].api.post.assert_not_called()



def wc_response_for_list_of_orders(nr_of_orders=5):
	"""
	Generate a dummy list of orders as if it was returned from the WooCommerce API
	"""
	return [deepcopy(dummy_wc_order) for i in range(nr_of_orders)]


dummy_wc_order = \
	{
		'_links': {'collection': [{'href': 'https://wootest.mysite.com/wp-json/wc/v3/orders'}],
					'self': [{'href': 'https://wootest.mysite.com/wp-json/wc/v3/orders/15'}]},
		'billing': {'address_1': '',
					'address_2': '',
					'city': '',
					'company': '',
					'country': '',
					'email': '',
					'first_name': '',
					'last_name': '',
					'phone': '',
					'postcode': '',
					'state': ''},
		'cart_hash': '',
		'cart_tax': '0.00',
		'coupon_lines': [],
		'created_via': 'admin',
		'currency': 'ZAR',
		'currency_symbol': 'R',
		'customer_id': 0,
		'customer_ip_address': '',
		'customer_note': '',
		'customer_user_agent': '',
		'date_completed': None,
		'date_completed_gmt': None,
		'date_created': '2023-05-20T13:12:23',
		'date_created_gmt': '2023-05-20T13:12:23',
		'date_modified': '2023-05-20T13:12:39',
		'date_modified_gmt': '2023-05-20T13:12:39',
		'date_paid': '2023-05-20T13:12:39',
		'date_paid_gmt': '2023-05-20T13:12:39',
		'discount_tax': '0.00',
		'discount_total': '0.00',
		'fee_lines': [],
		'id': 15,
		'is_editable': False,
		'line_items': [{'id': 2,
						'image': {'id': '12',
								'src': 'https://wootest.mysite.com/wp-content/uploads/2023/05/hoodie-with-logo-2.jpg'},
						'meta_data': [],
						'name': 'Hoodie',
						'parent_name': None,
						'price': 45,
						'product_id': 13,
						'quantity': 1,
						'sku': '',
						'subtotal': '45.00',
						'subtotal_tax': '0.00',
						'tax_class': '',
						'taxes': [],
						'total': '45.00',
						'total_tax': '0.00',
						'variation_id': 0}],
		'meta_data': [],
		'needs_payment': False,
		'needs_processing': True,
		'number': '15',
		'order_key': 'wc_order_YpxrBDm0nyUkk',
		'parent_id': 0,
		'payment_method': '',
		'payment_method_title': '',
		'payment_url': 'https://wootest.mysite.com/checkout/order-pay/15/?pay_for_order=true&key=wc_order_YpxrBDm0nyUkk',
		'prices_include_tax': False,
		'refunds': [],
		'shipping': {'address_1': '',
					'address_2': '',
					'city': '',
					'company': '',
					'country': '',
					'first_name': '',
					'last_name': '',
					'phone': '',
					'postcode': '',
					'state': ''},
		'shipping_lines': [],
		'shipping_tax': '0.00',
		'shipping_total': '0.00',
		'status': 'processing',
		'tax_lines': [],
		'total': '45.00',
		'total_tax': '0.00',
		'transaction_id': '',
		'version': '7.7.0'
	}