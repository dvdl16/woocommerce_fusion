import json
import os
from typing import List, Tuple

import frappe
from erpnext import get_default_company
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now

from woocommerce_fusion.woocommerce.woocommerce_api import WC_RESOURCE_DELIMITER

default_company = get_default_company()
default_bank = "Test Bank"
default_bank_account = "Checking Account"


class TestIntegrationWooCommerce(FrappeTestCase):
	"""
	Intended to be used as a Base class for integration tests with a WooCommerce website
	"""

	wc_server = None

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
		wc_servers = frappe.get_all(
			"WooCommerce Server", filters={"woocommerce_server_url": self.wc_url}
		)
		if len(wc_servers) == 0:
			wc_server = frappe.new_doc("WooCommerce Server")
		else:
			wc_server = frappe.get_doc("WooCommerce Server", wc_servers[0].name)
		wc_server.enable_sync = 1
		wc_server.woocommerce_server_url = self.wc_url
		wc_server.api_consumer_key = self.wc_consumer_key
		wc_server.api_consumer_secret = self.wc_consumer_secret
		wc_server.use_actual_tax_type = 1
		wc_server.tax_account = "VAT - SC"
		wc_server.f_n_f_account = "Freight and Forwarding Charges - SC"
		wc_server.creation_user = "test@erpnext.com"
		wc_server.company = "Some Company (Pty) Ltd"
		wc_server.item_group = "Products"
		wc_server.warehouse = "Stores - SC"
		wc_server.submit_sales_orders = 1
		wc_server.servers = []
		wc_server.enable_sync = 1
		wc_server.woocommerce_server_url = self.wc_url
		wc_server.api_consumer_key = self.wc_consumer_key
		wc_server.api_consumer_secret = self.wc_consumer_secret
		wc_server.enable_price_list_sync = 1
		wc_server.price_list = "_Test Price List"
		bank_account = create_bank_account()
		gl_account = create_gl_account_for_bank()
		wc_server.enable_payments_sync = 1
		wc_server.payment_method_bank_account_mapping = json.dumps({"bacs": bank_account.name})
		wc_server.payment_method_gl_account_mapping = json.dumps({"bacs": gl_account.name})

		wc_server.enable_stock_level_synchronisation = 1
		row = wc_server.append("warehouses")
		row.warehouse = "Stores - SC"

		row = wc_server.append("item_field_map")
		row.erpnext_field_name = "description | Description"
		row.woocommerce_field_name = "short_description"

		wc_server.save()
		self.wc_server = wc_server

		# Set WooCommerce Integration Settings
		settings = frappe.get_single("WooCommerce Integration Settings")
		one_year_ago = add_to_date(now(), years=-1)
		settings.wc_last_sync_date = one_year_ago
		settings.wc_last_sync_date_items = one_year_ago
		settings.save()

	def post_woocommerce_order(
		self,
		set_paid: bool = False,
		payment_method_title: str = "Direct Bank Transfer",
		item_price: float = 10,
		item_qty: int = 1,
		currency: str = None,
	) -> Tuple[str, str]:
		"""
		Create a dummy order on a WooCommerce testing site
		"""
		import json

		from requests_oauthlib import OAuth1Session

		# Create a product
		wc_product_id = self.post_woocommerce_product(
			product_name="ITEM_FOR_SALES_ORDER", regular_price=item_price
		)

		# Initialize OAuth1 session
		oauth = OAuth1Session(self.wc_consumer_key, client_secret=self.wc_consumer_secret)

		# API Endpoint
		url = f"{self.wc_url}/wp-json/wc/v3/orders/"

		data = {
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
			"line_items": [{"product_id": wc_product_id, "quantity": item_qty}],
		}

		if currency:
			data["currency"] = currency
		payload = json.dumps(data)
		headers = {"Content-Type": "application/json"}

		# Making the API call
		response = oauth.post(url, headers=headers, data=payload)

		id = response.json()["id"]
		return id, self.wc_server.name + WC_RESOURCE_DELIMITER + str(response.json()["id"])

	def post_woocommerce_product(
		self,
		product_name: str,
		opening_stock: float = 0,
		regular_price: float = 10,
		type: str = "simple",
		attributes: List[str] = ["Material Type", "Volume"],
	) -> int:
		"""
		Create a dummy product on a WooCommerce testing site
		"""
		import json

		from requests_oauthlib import OAuth1Session

		if type in ["variable", "variation"]:
			for attr in attributes:
				self.post_product_attribute(attr, attr.lower().replace(" ", "_"))

		# Create parent if required
		if type == "variation":
			parent_id = self.post_woocommerce_product(
				product_name + " parent", opening_stock, regular_price, "variable", attributes
			)

		# Initialize OAuth1 session
		oauth = OAuth1Session(self.wc_consumer_key, client_secret=self.wc_consumer_secret)

		# API Endpoint
		url = f"{self.wc_url}/wp-json/wc/v3/products/"
		url += f"{parent_id}/variations/" if type == "variation" else ""

		payload = {
			"name": product_name,
			"regular_price": str(regular_price),
			"description": "This is a new product",
			"short_description": product_name,
			"manage_stock": True,  # Enable stock management
			"stock_quantity": opening_stock,  # Set initial stock level
		}
		if type != "variation":
			payload["type"] = type
		if type == "variable":
			payload["attributes"] = [
				{
					"name": attr,
					"slug": attr.lower().replace(" ", "_"),
					"variation": True,
					"options": ["Option 1", "Option 2", "Option 3"],
				}
				for attr in attributes
			]
		elif type == "variation":
			payload["attributes"] = [
				{"name": attr, "slug": attr.lower().replace(" ", "_"), "option": "Option 1"}
				for attr in attributes
			]

		payload = json.dumps(payload)
		headers = {"Content-Type": "application/json"}

		# Making the API call
		response = oauth.post(url, headers=headers, data=payload)

		return response.json()["id"]

	def delete_woocommerce_order(self, wc_order_id: int) -> None:
		"""
		Delete an order on a WooCommerce testing site
		"""
		from requests_oauthlib import OAuth1Session

		# Initialize OAuth1 session
		oauth = OAuth1Session(self.wc_consumer_key, client_secret=self.wc_consumer_secret)

		# API Endpoint
		url = f"{self.wc_url}/wp-json/wc/v3/orders/{wc_order_id}"
		headers = {"Content-Type": "application/json"}

		# Making the API call
		oauth.delete(url, headers=headers)

	def delete_woocommerce_product(self, wc_product_id: int) -> None:
		"""
		Delete a product on a WooCommerce testing site
		"""
		from requests_oauthlib import OAuth1Session

		# Initialize OAuth1 session
		oauth = OAuth1Session(self.wc_consumer_key, client_secret=self.wc_consumer_secret)

		# API Endpoint
		url = f"{self.wc_url}/wp-json/wc/v3/products/{wc_product_id}?force=true"
		headers = {"Content-Type": "application/json"}

		# Making the API call
		oauth.delete(url, headers=headers)

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

	def get_woocommerce_product(self, product_id: int, parent_id: int = None) -> float:
		"""
		Get a product from a WooCommerce testing site
		"""
		from requests_oauthlib import OAuth1Session

		# Initialize OAuth1 session
		oauth = OAuth1Session(self.wc_consumer_key, client_secret=self.wc_consumer_secret)

		# API Endpoint
		url = (
			f"{self.wc_url}/wp-json/wc/v3/products/{product_id}"
			if not parent_id
			else f"{self.wc_url}/wp-json/wc/v3/products/{parent_id}/variations/{product_id}"
		)

		headers = {"Content-Type": "application/json"}

		# Making the API call
		response = oauth.get(url, headers=headers)

		product_data = response.json()

		return product_data

	def get_woocommerce_order(self, order_id: int) -> float:
		"""
		Get an order from a WooCommerce testing site
		"""
		from requests_oauthlib import OAuth1Session

		# Initialize OAuth1 session
		oauth = OAuth1Session(self.wc_consumer_key, client_secret=self.wc_consumer_secret)

		# API Endpoint
		url = f"{self.wc_url}/wp-json/wc/v3/orders/{order_id}"
		headers = {"Content-Type": "application/json"}

		# Making the API call
		response = oauth.get(url, headers=headers)

		order_data = response.json()

		return order_data

	def post_product_attribute(self, attribute_name: str, attribute_slug: str):
		"""
		Post product attribute to WooCommerce
		"""
		from requests_oauthlib import OAuth1Session

		# Initialize OAuth1 session
		oauth = OAuth1Session(self.wc_consumer_key, client_secret=self.wc_consumer_secret)

		# API Endpoint
		url = f"{self.wc_url}/wp-json/wc/v3/products/attributes"
		headers = {"Content-Type": "application/json"}

		data = {
			"name": attribute_name,
			"slug": attribute_slug,
			"type": "select",
		}

		# Making the API call
		response = oauth.post(url, data, headers=headers)
		attribute_data = response.json()

		return attribute_data


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
	return wc_server
