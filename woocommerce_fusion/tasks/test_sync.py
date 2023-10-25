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


class TestWooCommerceSync(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()  # important to call super() methods when extending TestCase.

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

	@patch("woocommerce_fusion.tasks.sync.frappe")
	def test_that_no_payment_entry_is_created_when_mapping_is_null(self, mock_frappe):
		# Arrange
		wc_order = {
			"payment_method": "EFT",
			"date_paid": "2023-01-01",
			"name": "wc_order_1",
			"payment_method_title": "EFT",
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
				payment_method_bank_account_mapping=json.dumps({"EFT": None}),
				payment_method_gl_account_mapping=json.dumps({"EFT": None}),
			)
		]

		mock_frappe.get_single.return_value = woocommerce_additional_settings
		mock_frappe.get_doc.return_value = mock_sales_order
		mock_frappe.get_value.return_value = "Test Company"
		mock_frappe.new_doc.return_value = MagicMock()

		# Act
		create_and_link_payment_entry(wc_order, sales_order_name)

		# Assert
		self.assertIsNone(mock_sales_order.woocommerce_payment_entry)
		mock_frappe.new_doc.assert_not_called()


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
