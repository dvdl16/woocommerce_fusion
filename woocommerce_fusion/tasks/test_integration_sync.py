import frappe

from woocommerce_fusion.tasks.sync_sales_orders import run_sales_orders_sync
from woocommerce_fusion.tasks.test_integration_helpers import TestIntegrationWooCommerce


class TestIntegrationWooCommerceSync(TestIntegrationWooCommerce):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()  # important to call super() methods when extending TestCase.

	def test_sync_create_new_sales_order_when_synchronising_with_woocommerce(self):
		"""
		Test that the Sales Order Synchornisation method creates new Sales orders when there are new
		WooCommerce orders.
		"""
		# Create a new order in WooCommerce
		wc_order_id = self.post_woocommerce_order(payment_method_title="Doge")

		# Run synchronisation
		run_sales_orders_sync()

		# Expect newly created Sales Order in ERPNext
		sales_order = frappe.get_doc("Sales Order", {"woocommerce_id": wc_order_id})
		self.assertIsNotNone(sales_order)

		# Expect correct payment method title on Sales Order
		self.assertEqual(sales_order.woocommerce_payment_method, "Doge")

	def test_sync_create_new_sales_order_and_pe_when_synchronising_with_woocommerce(self):
		"""
		Test that the Sales Order Synchornisation method creates new Sales orders and a Payment Entry
		when there are new fully paid WooCommerce orders.
		"""
		# Create a new order in WooCommerce
		wc_order_id = self.post_woocommerce_order(set_paid=True)

		# Run synchronisation
		run_sales_orders_sync()

		# Expect newly created Sales Order in ERPNext
		sales_order = frappe.get_doc("Sales Order", {"woocommerce_id": wc_order_id})
		self.assertIsNotNone(sales_order)

		# Expect linked Payment Entry in ERPNext
		sales_order = frappe.get_doc("Sales Order", {"woocommerce_id": wc_order_id})
		self.assertIsNotNone(sales_order)
		self.assertIsNotNone(sales_order.woocommerce_payment_entry)
