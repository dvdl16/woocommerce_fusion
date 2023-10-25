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


class TestWooCommerceSyncIntegration(FrappeTestCase):
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
