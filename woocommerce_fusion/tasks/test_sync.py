from unittest.mock import Mock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from woocommerce_fusion.tasks.sync import sync_sales_orders
from woocommerce_fusion.woocommerce.doctype.woocommerce_order.woocommerce_order import (
	generate_woocommerce_order_name_from_domain_and_id,
)


@patch("woocommerce_fusion.tasks.sync.frappe")
class TestWooCommerceOrder(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()  # important to call super() methods when extending TestCase.

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
