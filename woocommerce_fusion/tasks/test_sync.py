import os
from unittest.mock import Mock, patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now

from woocommerce_fusion.tasks.sync import sync_sales_orders
from woocommerce_fusion.woocommerce.doctype.woocommerce_order.woocommerce_order import (
	generate_woocommerce_order_name_from_domain_and_id,
)


class TestWooCommerceOrder(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()  # important to call super() methods when extending TestCase.

	def setUp(self):

		# Add WooCommerce Test Instance details
		self.wc_url = os.getenv("WOO_INTEGRATION_TESTS_WEBSERVER")
		self.wc_consumer_key = os.getenv("WOO_API_CONSUMER_KEY")
		self.wc_consumer_secret = os.getenv("WOO_API_CONSUMER_SECRET")
		if not all([self.wc_url, self.wc_consumer_key, self.wc_consumer_secret]):
			raise ValueError("Missing environment variables")

		# Set WooCommerce Settings
		woocommerce_additional_settings = frappe.get_single("Woocommerce Settings")
		woocommerce_additional_settings.enable_sync = 1
		woocommerce_additional_settings.woocommerce_server_url = self.wc_url
		woocommerce_additional_settings.api_consumer_key = self.wc_consumer_key
		woocommerce_additional_settings.api_consumer_secret = self.wc_consumer_secret
		woocommerce_additional_settings.tax_account = "VAT - SC"
		woocommerce_additional_settings.f_n_f_account = "Freight and Forwarding Charges - SC"
		woocommerce_additional_settings.creation_user = "test@erpnext.com"
		woocommerce_additional_settings.company = "Some Company (Pty) Ltd"
		woocommerce_additional_settings.save()

		# Set WooCommerce Additional Settings
		woocommerce_additional_settings = frappe.get_single("WooCommerce Additional Settings")
		woocommerce_additional_settings.wc_last_sync_date = (add_to_date(now(), days=-1),)
		row = woocommerce_additional_settings.append("servers")
		row.enable_sync = 1
		row.woocommerce_server_url = self.wc_url
		row.api_consumer_key = self.wc_consumer_key
		row.api_consumer_secret = self.wc_consumer_secret
		woocommerce_additional_settings.save()

	@patch("woocommerce_fusion.tasks.sync.frappe")
	@patch("woocommerce_fusion.tasks.sync.update_sales_order")
	@patch("woocommerce_fusion.tasks.sync.get_list_of_wc_orders_from_sales_order")
	def test_sync_sales_orders_while_passing_sales_order_should_update_sales_order_if_so_is_older(
		self, mock_get_wc_orders, mock_update_sales_order, mock_frappe
	):
		"""
		Test that the 'sync_sales_orders' function, when passed a sales order name,
		should update the sales order if the sales order is older than the corresponding WooCommerce order
		"""
		mock_frappe.get_doc.return_value = Mock()
		mock_frappe.get_single.return_value = Mock()

		woocommerce_site = "site1.example.com"
		woocommerce_id = 1

		# Create dummy Sales Order
		sales_order = frappe.get_doc({"doctype": "Sales Order"})
		sales_order.name = "SO-0001"
		sales_order.woocommerce_site = woocommerce_site
		sales_order.woocommerce_id = woocommerce_id
		sales_order.modified = "2023-01-01"
		mock_frappe.get_all.return_value = [sales_order]

		# Create dummy WooCommerce Order
		wc_order = frappe.get_doc({"doctype": "WooCommerce Order"})
		wc_order.woocommerce_site = woocommerce_site
		wc_order.id = woocommerce_id
		wc_order.name = generate_woocommerce_order_name_from_domain_and_id(
			woocommerce_site, woocommerce_id
		)
		wc_order.modified = "2023-12-31"
		mock_get_wc_orders.return_value = [wc_order.__dict__]

		# Call the method under test
		sync_sales_orders(sales_order_name="SO-0001")

		# Assert that the sales order need to be updated
		mock_update_sales_order.assert_called_once_with(wc_order.__dict__, "SO-0001")

	@patch("woocommerce_fusion.tasks.sync.frappe")
	@patch("woocommerce_fusion.tasks.sync.update_woocommerce_order")
	@patch("woocommerce_fusion.tasks.sync.get_list_of_wc_orders_from_sales_order")
	def test_sync_sales_orders_while_passing_sales_order_should_update_wc_order_if_so_is_newer(
		self, mock_get_wc_orders, mock_update_woocommerce_order, mock_frappe
	):
		"""
		Test that the 'sync_sales_orders' function, when passed a sales order name,
		should update the WooCommerce order if the sales order is newer than the corresponding WooCommerce order
		"""
		mock_frappe.get_doc.return_value = Mock()
		mock_frappe.get_single.return_value = Mock()

		woocommerce_site = "site1.example.com"
		woocommerce_id = 1

		# Create dummy Sales Order
		sales_order = frappe.get_doc({"doctype": "Sales Order"})
		sales_order.name = "SO-0001"
		sales_order.woocommerce_site = woocommerce_site
		sales_order.woocommerce_id = woocommerce_id
		sales_order.modified = "2023-12-25"
		mock_frappe.get_all.return_value = [sales_order]

		# Create dummy WooCommerce Order
		wc_order = frappe.get_doc({"doctype": "WooCommerce Order"})
		wc_order.woocommerce_site = woocommerce_site
		wc_order.id = woocommerce_id
		wc_order.name = generate_woocommerce_order_name_from_domain_and_id(
			woocommerce_site, woocommerce_id
		)
		wc_order.modified = "2023-01-01"
		mock_get_wc_orders.return_value = [wc_order.__dict__]

		# Call the method under test
		sync_sales_orders(sales_order_name="SO-0001")

		# Assert that the sales order need to be updated
		mock_update_woocommerce_order.assert_called_once_with(wc_order.__dict__, "SO-0001")

	@patch("woocommerce_fusion.tasks.sync.frappe")
	@patch("woocommerce_fusion.tasks.sync.create_sales_order")
	@patch("woocommerce_fusion.tasks.sync.get_list_of_wc_orders_from_sales_order")
	def test_sync_sales_orders_while_passing_sales_order_should_create_so_if__no_so(
		self, mock_get_wc_orders, mock_create_sales_order, mock_frappe
	):
		"""
		Test that the 'sync_sales_orders' function, when passed a sales order name,
		should create a Sales Order if there are no corresponding WooCommerce order
		"""
		mock_frappe.get_doc.return_value = Mock()
		mock_frappe.get_single.return_value = Mock()

		woocommerce_site = "site1.example.com"
		woocommerce_id = 1

		# Create dummy Sales Order
		sales_order = frappe.get_doc({"doctype": "Sales Order"})
		sales_order.name = "SO-0001"
		sales_order.woocommerce_site = woocommerce_site
		sales_order.woocommerce_id = 2
		mock_frappe.get_all.return_value = [sales_order]

		# Create dummy WooCommerce Order
		wc_order = frappe.get_doc({"doctype": "WooCommerce Order"})
		wc_order.woocommerce_site = woocommerce_site
		wc_order.id = woocommerce_id
		wc_order.name = generate_woocommerce_order_name_from_domain_and_id(
			woocommerce_site, woocommerce_id
		)
		mock_get_wc_orders.return_value = [wc_order.__dict__]

		# Call the method under test
		sync_sales_orders(sales_order_name="SO-0001")

		# Assert that the sales order need to be updated
		mock_create_sales_order.assert_called_once()
		self.assertEqual(mock_create_sales_order.call_args.args[0], wc_order.__dict__)

	def test_sync_create_new_sales_order_when_synchronising_with_woocommerce(self):
		""" """
		# Create a new order in WooCommerce
		wc_order_id = self.post_woocommerce_order()

		# Run synchronisation
		sync_sales_orders()

		# Expect newly created Sales Order in ERPNext
		sales_order = frappe.get_doc("Sales Order", {"woocommerce_id": wc_order_id})
		self.assertIsNotNone(sales_order)

	def post_woocommerce_order(self) -> int:
		"""
		Create a dummy order on a WooCommerce testing site
		"""
		import json

		from requests_oauthlib import OAuth1Session

		# Initialize OAuth1 session
		oauth = OAuth1Session(self.wc_consumer_key, client_secret=self.wc_consumer_secret)

		# API Endpoint
		url = f"{self.wc_url}/wp-json/wc/v3/orders/"

		payload = json.dumps(
			{
				"payment_method": "bacs",
				"payment_method_title": "Direct Bank Transfer",
				"set_paid": False,
				"billing": {
					"first_name": "John",
					"last_name": "Doe",
					"address_1": "123 Main St",
					"address_2": "",
					"city": "Anytown",
					"state": "CA",
					"postcode": "12345",
					"country": "US",
					"email": "john.doe@example.com",
					"phone": "123-456-7890",
				},
				"shipping": {
					"first_name": "John",
					"last_name": "Doe",
					"address_1": "123 Main St",
					"address_2": "",
					"city": "Anytown",
					"state": "CA",
					"postcode": "12345",
					"country": "US",
				},
				"line_items": [{"product_id": 548, "quantity": 1}],
			}
		)
		headers = {"Content-Type": "application/json"}

		# Making the API call
		response = oauth.post(url, headers=headers, data=payload)

		return response.json()["id"]
