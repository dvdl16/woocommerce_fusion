import json
import os

import frappe
from erpnext import get_default_company
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now

default_company = get_default_company()
default_bank = "Test Bank"
default_bank_account = "Checking Account"


class TestIntegrationWooCommerce(FrappeTestCase):
	"""
	Intended to be used as a Base class for integration tests with a WooCommerce website
	"""

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
		woocommerce_settings = frappe.get_single("WooCommerce Integration Settings")
		woocommerce_settings.enable_sync = 1
		woocommerce_settings.woocommerce_server_url = self.wc_url
		woocommerce_settings.api_consumer_key = self.wc_consumer_key
		woocommerce_settings.api_consumer_secret = self.wc_consumer_secret
		woocommerce_settings.tax_account = "VAT - SC"
		woocommerce_settings.f_n_f_account = "Freight and Forwarding Charges - SC"
		woocommerce_settings.creation_user = "test@erpnext.com"
		woocommerce_settings.company = "Some Company (Pty) Ltd"
		woocommerce_settings.item_group = "Products"
		woocommerce_settings.warehouse = "Stores - SC"
		woocommerce_settings.submit_sales_orders = 1
		woocommerce_settings.wc_last_sync_date = add_to_date(now(), days=-1)
		woocommerce_settings.servers = []
		row = woocommerce_settings.append("servers")
		row.enable_sync = 1
		row.woocommerce_server = get_woocommerce_server(self.wc_url).name
		row.woocommerce_server_url = self.wc_url
		row.api_consumer_key = self.wc_consumer_key
		row.api_consumer_secret = self.wc_consumer_secret
		row.enable_price_list_sync = 1
		row.price_list = "_Test Price List"
		bank_account = create_bank_account()
		gl_account = create_gl_account_for_bank()
		row.enable_payments_sync = 1
		row.payment_method_bank_account_mapping = json.dumps({"bacs": bank_account.name})
		row.payment_method_gl_account_mapping = json.dumps({"bacs": gl_account.name})

		woocommerce_settings.save()

	def post_woocommerce_order(
		self, set_paid: bool = False, payment_method_title: str = "Direct Bank Transfer"
	) -> int:
		"""
		Create a dummy order on a WooCommerce testing site
		"""
		import json

		from requests_oauthlib import OAuth1Session

		# Create a product
		wc_product_id = self.post_woocommerce_product(product_name="ITEM_FOR_SALES_ORDER")

		# Initialize OAuth1 session
		oauth = OAuth1Session(self.wc_consumer_key, client_secret=self.wc_consumer_secret)

		# API Endpoint
		url = f"{self.wc_url}/wp-json/wc/v3/orders/"

		payload = json.dumps(
			{
				"payment_method": "bacs",
				"payment_method_title": payment_method_title,
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
				"line_items": [{"product_id": wc_product_id, "quantity": 1}],
			}
		)
		headers = {"Content-Type": "application/json"}

		# Making the API call
		response = oauth.post(url, headers=headers, data=payload)

		return response.json()["id"]

	def post_woocommerce_product(
		self, product_name: str, opening_stock: float = 0, regular_price: float = 10
	) -> int:
		"""
		Create a dummy product on a WooCommerce testing site
		"""
		import json

		from requests_oauthlib import OAuth1Session

		# Initialize OAuth1 session
		oauth = OAuth1Session(self.wc_consumer_key, client_secret=self.wc_consumer_secret)

		# API Endpoint
		url = f"{self.wc_url}/wp-json/wc/v3/products/"

		payload = json.dumps(
			{
				"name": product_name,
				"type": "simple",
				"regular_price": str(regular_price),
				"description": "This is a new product",
				"short_description": "New Product",
				"manage_stock": True,  # Enable stock management
				"stock_quantity": opening_stock,  # Set initial stock level
			}
		)

		headers = {"Content-Type": "application/json"}

		# Making the API call
		response = oauth.post(url, headers=headers, data=payload)

		return response.json()["id"]

	def get_woocommerce_product_stock_level(self, product_id: int) -> float:
		"""
		Get a products stock quantity from a WooCommerce testing site
		"""
		from requests_oauthlib import OAuth1Session

		# Initialize OAuth1 session
		oauth = OAuth1Session(self.wc_consumer_key, client_secret=self.wc_consumer_secret)

		# API Endpoint
		url = f"{self.wc_url}/wp-json/wc/v3/products/{product_id}"
		headers = {"Content-Type": "application/json"}

		# Making the API call
		response = oauth.get(url, headers=headers)

		product_data = response.json()
		stock_quantity = product_data.get("stock_quantity", "Not available")

		return stock_quantity

	def get_woocommerce_product_price(self, product_id: int) -> float:
		"""
		Get a product's price from a WooCommerce testing site
		"""
		from requests_oauthlib import OAuth1Session

		# Initialize OAuth1 session
		oauth = OAuth1Session(self.wc_consumer_key, client_secret=self.wc_consumer_secret)

		# API Endpoint
		url = f"{self.wc_url}/wp-json/wc/v3/products/{product_id}"
		headers = {"Content-Type": "application/json"}

		# Making the API call
		response = oauth.get(url, headers=headers)

		product_data = response.json()
		price = product_data.get("price", "Not available")

		return price


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
	except frappe.ValidationError:
		bank_account_doc = frappe.get_all(
			"Bank Account",
			{
				"account_name": default_bank_account,
				"bank": bank_name,
				"account": gl_account.name,
				"company": company,
			},
		)[0]

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


def get_woocommerce_server(woocommerce_server_url: str):
	wc_servers = frappe.get_all(
		"WooCommerce Server", filters={"woocommerce_server_url": woocommerce_server_url}
	)
	wc_server = wc_servers[0] if len(wc_servers) > 0 else None
	if not wc_server:
		wc_server = frappe.new_doc("WooCommerce Server")
		wc_server.woocommerce_server_url = woocommerce_server_url
		wc_server.save()
	return wc_server
