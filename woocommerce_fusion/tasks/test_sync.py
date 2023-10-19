import json
import os
from unittest.mock import MagicMock, Mock, patch

import frappe
from erpnext import get_default_company
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now

from woocommerce_fusion.tasks.sync import create_and_link_payment_entry, sync_sales_orders
from woocommerce_fusion.woocommerce.doctype.woocommerce_order.woocommerce_order import (
	generate_woocommerce_order_name_from_domain_and_id,
)

default_company = get_default_company()
default_bank = "Test Bank"
default_bank_account = "Checking Account"


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
		woocommerce_settings = frappe.get_single("Woocommerce Settings")
		woocommerce_settings.enable_sync = 1
		woocommerce_settings.woocommerce_server_url = self.wc_url
		woocommerce_settings.api_consumer_key = self.wc_consumer_key
		woocommerce_settings.api_consumer_secret = self.wc_consumer_secret
		woocommerce_settings.tax_account = "VAT - SC"
		woocommerce_settings.f_n_f_account = "Freight and Forwarding Charges - SC"
		woocommerce_settings.creation_user = "test@erpnext.com"
		woocommerce_settings.company = "Some Company (Pty) Ltd"
		woocommerce_settings.save()

		# Set WooCommerce Additional Settings
		woocommerce_additional_settings = frappe.get_single("WooCommerce Additional Settings")
		woocommerce_additional_settings.wc_last_sync_date = add_to_date(now(), days=-1)
		woocommerce_additional_settings.servers = []
		row = woocommerce_additional_settings.append("servers")
		row.enable_sync = 1
		row.woocommerce_server_url = self.wc_url
		row.api_consumer_key = self.wc_consumer_key
		row.api_consumer_secret = self.wc_consumer_secret
		bank_account = create_bank_account()
		gl_account = create_gl_account_for_bank()
		row.enable_payments_sync = 1
		row.payment_method_bank_account_mapping = json.dumps({"bacs": bank_account.name})
		row.payment_method_gl_account_mapping = json.dumps({"bacs": gl_account.name})
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
		"""
		Test that the Sales Order Synchornisation method creates new Sales orders when there are new
		WooCommerce orders.
		"""
		# Create a new order in WooCommerce
		wc_order_id = self.post_woocommerce_order()

		# Run synchronisation
		sync_sales_orders()

		# Expect newly created Sales Order in ERPNext
		sales_order = frappe.get_doc("Sales Order", {"woocommerce_id": wc_order_id})
		self.assertIsNotNone(sales_order)

	def test_sync_create_new_sales_order_and_pe_when_synchronising_with_woocommerce(self):
		"""
		Test that the Sales Order Synchornisation method creates new Sales orders and a Payment Entry
		when there are new fully paid WooCommerce orders.
		"""
		# Create a new order in WooCommerce
		wc_order_id = self.post_woocommerce_order(set_paid=True)

		# Run synchronisation
		sync_sales_orders()

		# Expect newly created Sales Order in ERPNext
		sales_order = frappe.get_doc("Sales Order", {"woocommerce_id": wc_order_id})
		self.assertIsNotNone(sales_order)

		# Expect linked Payment Entry in ERPNext
		sales_order = frappe.get_doc("Sales Order", {"woocommerce_id": wc_order_id})
		self.assertIsNotNone(sales_order)
		self.assertIsNotNone(sales_order.woocommerce_payment_entry)

	@patch("woocommerce_fusion.tasks.sync.frappe")
	def test_successful_payment_entry_creation(self, mock_frappe):
		# Arrange
		wc_order = {
			"payment_method": "PayPal",
			"date_paid": "2023-01-01",
			"name": "wc_order_1",
			"payment_method_title": "PayPal",
		}
		sales_order_name = "SO-0001"

		mock_sales_order = MagicMock()
		mock_sales_order.woocommerce_site = "example.com"
		mock_sales_order.woocommerce_payment_entry = None
		mock_sales_order.customer = "customer_1"
		mock_sales_order.grand_total = 100
		mock_sales_order.name = "SO-0001"

		woocommerce_additional_settings = MagicMock()
		woocommerce_additional_settings.servers = [
			frappe._dict(
				enable_payments_sync=1,
				woocommerce_server_url="http://example.com",
				payment_method_bank_account_mapping=json.dumps({"PayPal": "Bank Account"}),
				payment_method_gl_account_mapping=json.dumps({"PayPal": "GL Account"}),
			)
		]

		mock_frappe.get_single.return_value = woocommerce_additional_settings
		mock_frappe.get_doc.return_value = mock_sales_order
		mock_frappe.get_value.return_value = "Test Company"
		mock_frappe.new_doc.return_value = MagicMock()

		# Act
		create_and_link_payment_entry(wc_order, sales_order_name)

		# Assert
		self.assertIsNotNone(mock_sales_order.woocommerce_payment_entry)
		mock_frappe.new_doc.assert_called_once_with("Payment Entry")

	def post_woocommerce_order(self, set_paid: bool = False) -> int:
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
				"set_paid": set_paid,
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


def create_bank_account(
	bank_name=default_bank, account_name="_Test Bank", company=default_company
):

	try:
		gl_account = frappe.get_doc(
			{
				"doctype": "Account",
				"company": company,
				"account_name": account_name,
				"parent_account": "Bank Accounts - SC",
				"account_number": "1",
			}
		).insert(ignore_if_duplicate=True)
	except frappe.DuplicateEntryError:
		pass

	try:
		frappe.get_doc(
			{
				"doctype": "Bank",
				"bank_name": bank_name,
			}
		).insert(ignore_if_duplicate=True)
	except frappe.DuplicateEntryError:
		pass

	try:
		bank_account_doc = frappe.get_doc(
			{
				"doctype": "Bank Account",
				"account_name": default_bank_account,
				"bank": bank_name,
				"account": gl_account.name,
				"is_company_account": 1,
				"company": company,
			}
		).insert(ignore_if_duplicate=True)
	except frappe.DuplicateEntryError:
		pass

	return bank_account_doc


def create_gl_account_for_bank(account_name="_Test Bank"):
	try:
		gl_account = frappe.get_doc(
			{
				"doctype": "Account",
				"company": get_default_company(),
				"account_name": account_name,
				"parent_account": "Bank Accounts - SC",
				"type": "Bank",
			}
		).insert(ignore_if_duplicate=True)
	except frappe.DuplicateEntryError:
		pass

	return frappe.get_doc("Account", {"account_name": account_name})
