from unittest.mock import patch

import frappe

from woocommerce_fusion.tasks.sync_sales_orders import run_sales_orders_sync
from woocommerce_fusion.tasks.test_integration_helpers import TestIntegrationWooCommerce


@patch("woocommerce_fusion.tasks.sync_sales_orders.frappe.log_error")
class TestIntegrationWooCommerceSync(TestIntegrationWooCommerce):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()  # important to call super() methods when extending TestCase.

	def test_sync_create_new_sales_order_when_synchronising_with_woocommerce(self, mock_log_error):
		"""
		Test that the Sales Order Synchornisation method creates new Sales orders when there are new
		WooCommerce orders.

		Assumes that the Wordpress Site we're testing against has:
		- Tax enabled
		- Sales prices include tax
		"""
		# Create a new order in WooCommerce
		wc_order_id = self.post_woocommerce_order(payment_method_title="Doge", item_price=10, item_qty=1)

		# Run synchronisation
		run_sales_orders_sync()

		# Expect no errors logged
		mock_log_error.assert_not_called()

		# Expect newly created Sales Order in ERPNext
		sales_order = frappe.get_doc("Sales Order", {"woocommerce_id": wc_order_id})
		self.assertIsNotNone(sales_order)

		# Expect correct payment method title on Sales Order
		self.assertEqual(sales_order.woocommerce_payment_method, "Doge")

		# Expect correct items in Sales Order
		self.assertEqual(sales_order.items[0].rate, 8.7)
		self.assertEqual(sales_order.items[0].qty, 1)

		# Delete order in WooCommerce
		self.delete_woocommerce_order(wc_order_id=wc_order_id)

	def test_sync_create_new_sales_order_and_pe_when_synchronising_with_woocommerce(
		self, mock_log_error
	):
		"""
		Test that the Sales Order Synchornisation method creates new Sales orders and a Payment Entry
		when there are new fully paid WooCommerce orders.
		"""
		# Create a new order in WooCommerce
		wc_order_id = self.post_woocommerce_order(set_paid=True)

		# Run synchronisation
		run_sales_orders_sync()
		mock_log_error.assert_not_called()

		# Expect newly created Sales Order in ERPNext
		sales_order = frappe.get_doc("Sales Order", {"woocommerce_id": wc_order_id})
		self.assertIsNotNone(sales_order)

		# Expect linked Payment Entry in ERPNext
		sales_order = frappe.get_doc("Sales Order", {"woocommerce_id": wc_order_id})
		self.assertIsNotNone(sales_order)
		self.assertIsNotNone(sales_order.woocommerce_payment_entry)

		# Delete order in WooCommerce
		self.delete_woocommerce_order(wc_order_id=wc_order_id)

	def test_sync_create_new_draft_sales_order_when_synchronising_with_woocommerce(
		self, mock_log_error
	):
		"""
		Test that the Sales Order Synchornisation method creates new Draft Sales orders without errors
		when the submit_sales_orders setting is set to 0
		"""
		# Setup
		woocommerce_settings = frappe.get_single("WooCommerce Integration Settings")
		woocommerce_settings.submit_sales_orders = 0
		woocommerce_settings.save()

		# Create a new order in WooCommerce
		wc_order_id = self.post_woocommerce_order(set_paid=True)

		# Run synchronisation
		run_sales_orders_sync()
		mock_log_error.assert_not_called()

		# Expect newly created Sales Order in ERPNext
		sales_order = frappe.get_doc("Sales Order", {"woocommerce_id": wc_order_id})
		self.assertIsNotNone(sales_order)

		# Teardown
		woocommerce_settings = frappe.get_single("WooCommerce Integration Settings")
		woocommerce_settings.submit_sales_orders = 1
		woocommerce_settings.save()

		# Delete order in WooCommerce
		self.delete_woocommerce_order(wc_order_id=wc_order_id)

	def test_sync_link_payment_entry_after_so_submitted_when_synchronising_with_woocommerce(
		self, mock_log_error
	):
		"""
		Test that the Sales Order Synchornisation method creates a linked Payment Entry if there are no linked
		PE's on a now-submitted Sales Order
		"""
		# Setup
		woocommerce_settings = frappe.get_single("WooCommerce Integration Settings")
		woocommerce_settings.submit_sales_orders = 0
		woocommerce_settings.save()

		# Create a new order in WooCommerce
		wc_order_id = self.post_woocommerce_order(set_paid=True)

		# Run synchronisation
		run_sales_orders_sync()
		mock_log_error.assert_not_called()

		# Expect no linked Payment Entry
		sales_order = frappe.get_doc("Sales Order", {"woocommerce_id": wc_order_id})
		self.assertIsNone(sales_order.woocommerce_payment_entry)
		self.assertEqual(sales_order.custom_attempted_woocommerce_auto_payment_entry, 0)

		# Action: Submit the Sales Order
		sales_order.submit()

		# Run synchronisation again
		run_sales_orders_sync(sales_order_name=sales_order.name)
		mock_log_error.assert_not_called()

		# Expect linked Payment Entry this time
		sales_order = frappe.get_doc("Sales Order", {"woocommerce_id": wc_order_id})
		self.assertIsNotNone(sales_order.woocommerce_payment_entry)
		self.assertEqual(sales_order.custom_attempted_woocommerce_auto_payment_entry, 1)

		# Teardown
		woocommerce_settings = frappe.get_single("WooCommerce Integration Settings")
		woocommerce_settings.submit_sales_orders = 1
		woocommerce_settings.save()

		# Delete order in WooCommerce
		self.delete_woocommerce_order(wc_order_id=wc_order_id)
