import json
from unittest.mock import MagicMock, Mock, patch

import frappe
from erpnext import get_default_company
from frappe.tests.utils import FrappeTestCase

from woocommerce_fusion.tasks.sync_sales_orders import SynchroniseSalesOrders
from woocommerce_fusion.woocommerce.woocommerce_api import (
	generate_woocommerce_record_name_from_domain_and_id,
)

default_company = get_default_company()
default_bank = "Test Bank"
default_bank_account = "Checking Account"


class TestWooCommerceSync(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()  # important to call super() methods when extending TestCase.

	@patch.object(SynchroniseSalesOrders, "update_sales_order")
	def test_sync_sales_orders_while_passing_sales_order_should_update_sales_order_if_so_is_older(
		self, mock_update_sales_order
	):
		"""
		Test that the 'sync_sales_orders' function should update the sales order
		if the sales order is older than the corresponding WooCommerce order
		"""
		# Initialise class
		sync = SynchroniseSalesOrders(servers=Mock())

		woocommerce_server = "site1.example.com"
		woocommerce_id = 1

		# Create dummy Sales Order
		sales_order = frappe.get_doc({"doctype": "Sales Order"})
		sales_order.name = "SO-0001"
		sales_order.woocommerce_server = woocommerce_server
		sales_order.woocommerce_id = woocommerce_id
		sales_order.modified = "2023-01-01"
		sync.sales_orders_list = [sales_order]

		# Create dummy WooCommerce Order
		wc_order = frappe.get_doc({"doctype": "WooCommerce Order"})
		wc_order.woocommerce_server = woocommerce_server
		wc_order.id = woocommerce_id
		wc_order.name = generate_woocommerce_record_name_from_domain_and_id(
			woocommerce_server, woocommerce_id
		)
		wc_order.date_modified = "2023-12-31"
		sync.wc_orders_dict = {wc_order.name: wc_order.__dict__}

		# Call the method under test
		sync.sync_wc_orders_with_erpnext_sales_orders()

		# Assert that the sales order need to be updated
		mock_update_sales_order.assert_called_once_with(wc_order.__dict__, "SO-0001")

	@patch("woocommerce_fusion.tasks.sync_sales_orders.frappe")
	@patch.object(SynchroniseSalesOrders, "update_woocommerce_order")
	def test_sync_sales_orders_while_passing_sales_order_should_update_wc_order_if_so_is_newer(
		self, mock_update_woocommerce_order, mock_frappe
	):
		"""
		Test that the 'sync_sales_orders' function should update the WooCommerce order
		if the sales order is newer than the corresponding WooCommerce order
		"""
		# Initialise class
		sync = SynchroniseSalesOrders(servers=Mock())

		mock_frappe.get_doc.return_value = Mock()
		mock_frappe.get_single.return_value = Mock()

		woocommerce_server = "site1.example.com"
		woocommerce_id = 1

		# Create dummy Sales Order
		sales_order = frappe.get_doc({"doctype": "Sales Order"})
		sales_order.name = "SO-0001"
		sales_order.woocommerce_server = woocommerce_server
		sales_order.woocommerce_id = woocommerce_id
		sales_order.modified = "2023-12-25"
		sales_order.docstatus = 1
		sync.sales_orders_list = [sales_order]

		# Create dummy WooCommerce Order
		wc_order = frappe.get_doc({"doctype": "WooCommerce Order"})
		wc_order.woocommerce_server = woocommerce_server
		wc_order.id = woocommerce_id
		wc_order.name = generate_woocommerce_record_name_from_domain_and_id(
			woocommerce_server, woocommerce_id
		)
		wc_order.date_modified = "2023-01-01"
		sync.wc_orders_dict = {wc_order.name: wc_order.__dict__}

		# Call the method under test
		sync.sync_wc_orders_with_erpnext_sales_orders()

		# Assert that the sales order need to be updated
		mock_update_woocommerce_order.assert_called_once_with(wc_order.__dict__, "SO-0001")

	@patch("woocommerce_fusion.tasks.sync.frappe")
	@patch.object(SynchroniseSalesOrders, "create_sales_order")
	def test_sync_sales_orders_while_passing_sales_order_should_create_so_if_no_so(
		self, mock_create_sales_order, mock_frappe
	):
		"""
		Test that the 'sync_sales_orders' function should create a Sales Order if
		there are no corresponding Sales orders
		"""
		# Initialise class
		sync = SynchroniseSalesOrders(sales_order_name="SO-0001")

		mock_frappe.get_doc.return_value = Mock()
		mock_frappe.get_single.return_value = Mock()

		woocommerce_server = "site1.example.com"
		woocommerce_id = 1

		# Create dummy Sales Order
		sales_order = frappe.get_doc({"doctype": "Sales Order"})
		sales_order.name = "SO-0001"
		sales_order.woocommerce_server = woocommerce_server
		sales_order.woocommerce_id = 2
		sync.sales_orders_list = [sales_order]

		# Create dummy WooCommerce Order
		wc_order = frappe.get_doc({"doctype": "WooCommerce Order"})
		wc_order.woocommerce_server = woocommerce_server
		wc_order.id = woocommerce_id
		wc_order.name = generate_woocommerce_record_name_from_domain_and_id(
			woocommerce_server, woocommerce_id
		)
		sync.wc_orders_dict = {wc_order.name: wc_order.__dict__}

		# Call the method under test
		sync.sync_wc_orders_with_erpnext_sales_orders()

		# Assert that the sales order need to be updated
		mock_create_sales_order.assert_called_once()
		self.assertEqual(mock_create_sales_order.call_args.args[0], wc_order.__dict__)

	@patch("woocommerce_fusion.tasks.sync_sales_orders.frappe")
	def test_successful_payment_entry_creation(self, mock_frappe):
		# Initialise class
		sync = SynchroniseSalesOrders()

		# Arrange
		wc_order = {
			"payment_method": "PayPal",
			"date_paid": "2023-01-01",
			"name": "wc_order_1",
			"payment_method_title": "PayPal",
			"total": 100,
		}
		sales_order_name = "SO-0001"

		mock_sales_order = MagicMock()
		mock_sales_order.woocommerce_server = "example.com"
		mock_sales_order.woocommerce_payment_entry = None
		mock_sales_order.customer = "customer_1"
		mock_sales_order.grand_total = 100
		mock_sales_order.name = "SO-0001"
		mock_sales_order.docstatus = 1
		mock_sales_order.per_billed = 0

		mock_frappe.get_cached_doc.return_value = frappe._dict(
			enable_payments_sync=1,
			woocommerce_server_url="http://example.com",
			payment_method_bank_account_mapping=json.dumps({"PayPal": "Bank Account"}),
			payment_method_gl_account_mapping=json.dumps({"PayPal": "GL Account"}),
		)

		mock_frappe.get_doc.return_value = mock_sales_order
		mock_frappe.get_value.return_value = "Test Company"
		mock_frappe.new_doc.return_value = MagicMock()

		# Act
		sync.create_and_link_payment_entry(wc_order, sales_order_name)

		# Assert
		self.assertIsNotNone(mock_sales_order.woocommerce_payment_entry)
		mock_frappe.new_doc.assert_called_once_with("Payment Entry")

	@patch("woocommerce_fusion.tasks.sync_sales_orders.frappe")
	def test_that_no_payment_entry_is_created_when_mapping_is_null(self, mock_frappe):
		# Arrange
		sync = SynchroniseSalesOrders()
		wc_order = {
			"payment_method": "EFT",
			"date_paid": "2023-01-01",
			"name": "wc_order_1",
			"payment_method_title": "EFT",
		}
		sales_order_name = "SO-0001"

		mock_sales_order = MagicMock()
		mock_sales_order.woocommerce_server = "example.com"
		mock_sales_order.woocommerce_payment_entry = None
		mock_sales_order.customer = "customer_1"
		mock_sales_order.grand_total = 100
		mock_sales_order.name = "SO-0001"

		mock_frappe.get_cached_doc.return_value = frappe._dict(
			enable_payments_sync=1,
			woocommerce_server_url="http://example.com",
			payment_method_bank_account_mapping=json.dumps({"EFT": None}),
			payment_method_gl_account_mapping=json.dumps({"EFT": None}),
		)

		mock_frappe.get_doc.return_value = mock_sales_order
		mock_frappe.get_value.return_value = "Test Company"
		mock_frappe.new_doc.return_value = MagicMock()

		# Act
		sync.create_and_link_payment_entry(wc_order, sales_order_name)

		# Assert
		self.assertIsNone(mock_sales_order.woocommerce_payment_entry)
		mock_frappe.new_doc.assert_not_called()

	@patch("woocommerce_fusion.tasks.sync_sales_orders.frappe")
	def test_payment_entry_created_with_sales_invoice_as_reference(self, mock_frappe):
		"""
		Test that the created Payment Entry's reference is set to the linked Sales Invoice when
		a Sales Invoice is already created for the Sales Order
		"""
		# Initialise class
		sync = SynchroniseSalesOrders()

		# Arrange
		wc_order = {
			"payment_method": "PayPal",
			"date_paid": "2023-01-01",
			"name": "wc_order_1",
			"payment_method_title": "PayPal",
			"total": 100,
		}
		sales_order_name = "SO-0001"

		mock_sales_order = MagicMock()
		mock_sales_order.woocommerce_server = "example.com"
		mock_sales_order.woocommerce_payment_entry = None
		mock_sales_order.customer = "customer_1"
		mock_sales_order.grand_total = 100
		mock_sales_order.name = "SO-0001"
		mock_sales_order.docstatus = 1
		mock_sales_order.per_billed = 1

		mock_sales_invoice_item = MagicMock()
		mock_sales_invoice_item.parent = "INVOICE-12345"

		mock_frappe.get_cached_doc.return_value = frappe._dict(
			enable_payments_sync=1,
			woocommerce_server_url="http://example.com",
			payment_method_bank_account_mapping=json.dumps({"PayPal": "Bank Account"}),
			payment_method_gl_account_mapping=json.dumps({"PayPal": "GL Account"}),
		)

		mock_frappe.get_doc.return_value = mock_sales_order
		mock_frappe.get_all.return_value = [mock_sales_invoice_item]
		mock_frappe.get_value.return_value = "Test Company"
		mock_frappe.new_doc.return_value = MagicMock()

		# Act
		sync.create_and_link_payment_entry(wc_order, sales_order_name)

		# Assert
		self.assertIsNotNone(mock_sales_order.woocommerce_payment_entry)
		mock_frappe.new_doc.assert_called_once_with("Payment Entry")


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
