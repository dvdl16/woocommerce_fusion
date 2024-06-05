from unittest.mock import patch

import frappe
from erpnext import get_default_company
from erpnext.stock.doctype.item.test_item import create_item

from woocommerce_fusion.tasks.sync_sales_orders import (
	get_tax_inc_price_for_woocommerce_line_item,
	run_sales_orders_sync,
)
from woocommerce_fusion.tasks.test_integration_helpers import (
	TestIntegrationWooCommerce,
	get_woocommerce_server,
)


@patch("woocommerce_fusion.tasks.sync_sales_orders.frappe.log_error")
class TestIntegrationWooCommerceSync(TestIntegrationWooCommerce):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()  # important to call super() methods when extending TestCase.

	def _create_sales_taxes_and_charges_template(
		self, wc_server, rate: float, included_in_rate: bool = False
	) -> str:
		taxes_and_charges_template = frappe.get_doc(
			{
				"company": wc_server.company,
				"doctype": "Sales Taxes and Charges Template",
				"taxes": [
					{
						"account_head": wc_server.tax_account,
						"charge_type": "On Net Total",
						"description": "VAT",
						"doctype": "Sales Taxes and Charges",
						"parentfield": "taxes",
						"rate": rate,
						"included_in_print_rate": included_in_rate,
					}
				],
				"title": "_Test Sales Taxes and Charges Template for Woo",
			}
		).insert(ignore_if_duplicate=True)
		return taxes_and_charges_template.name

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

		# Expect correct tax rows in Sales Order
		self.assertEqual(sales_order.taxes[0].charge_type, "Actual")
		self.assertEqual(sales_order.taxes[0].rate, 0)
		self.assertEqual(sales_order.taxes[0].tax_amount, 1.3)
		self.assertEqual(sales_order.taxes[0].total, 10)
		self.assertEqual(sales_order.taxes[0].account_head, "VAT - SC")

		# Delete order in WooCommerce
		self.delete_woocommerce_order(wc_order_id=wc_order_id)

	def test_sync_create_new_sales_order_with_tax_template_when_synchronising_with_woocommerce(
		self, mock_log_error
	):
		"""
		Test that the Sales Order Synchornisation method creates new Sales orders with a Tax Template
		when there are new WooCommerce orders and a Sales Taxes and Charges template has been set in settings.

		Assumes that the Wordpress Site we're testing against has:
		- Tax enabled
		- Sales prices include tax
		"""
		# Setup
		wc_server = frappe.get_doc("WooCommerce Server", self.wc_server.name)
		template_name = self._create_sales_taxes_and_charges_template(
			wc_server, rate=15, included_in_rate=1
		)
		wc_server.use_actual_tax_type = 0
		wc_server.sales_taxes_and_charges_template = template_name
		wc_server.flags.ignore_mandatory = True
		wc_server.save()

		# Create a new order in WooCommerce
		wc_order_id = self.post_woocommerce_order(payment_method_title="Doge", item_price=10, item_qty=2)

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
		self.assertEqual(sales_order.items[0].rate, 10)  # should show tax inclusive price
		self.assertEqual(sales_order.items[0].qty, 2)

		# Expect correct tax rows in Sales Order
		self.assertEqual(sales_order.taxes[0].charge_type, "On Net Total")
		self.assertEqual(sales_order.taxes[0].rate, 15)
		self.assertEqual(sales_order.taxes[0].tax_amount, 2.61)  # 20 x 15/115 = 2.61
		self.assertEqual(sales_order.taxes[0].total, 20)
		self.assertEqual(sales_order.taxes[0].account_head, "VAT - SC")

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
		wc_server = frappe.get_doc("WooCommerce Server", self.wc_server.name)
		wc_server.submit_sales_orders = 0
		wc_server.flags.ignore_mandatory = True
		wc_server.save()

		# Create a new order in WooCommerce
		wc_order_id = self.post_woocommerce_order(set_paid=True)

		# Run synchronisation
		run_sales_orders_sync()
		mock_log_error.assert_not_called()

		# Expect newly created Sales Order in ERPNext
		sales_order = frappe.get_doc("Sales Order", {"woocommerce_id": wc_order_id})
		self.assertIsNotNone(sales_order)

		# Teardown
		wc_server = frappe.get_doc("WooCommerce Server", self.wc_server.name)
		wc_server.submit_sales_orders = 1
		wc_server.flags.ignore_mandatory = True
		wc_server.save()

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
		wc_server = frappe.get_doc("WooCommerce Server", self.wc_server.name)
		wc_server.submit_sales_orders = 0
		wc_server.flags.ignore_mandatory = True
		wc_server.save()

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

		# Delete order in WooCommerce
		self.delete_woocommerce_order(wc_order_id=wc_order_id)

	def test_sync_updates_woocommerce_order_when_synchronising_with_woocommerce(self, mock_log_error):
		"""
		Test that the Sales Order Synchornisation method updates a WooCommerce Order
		with changed fields from Sales Order
		"""
		# Setup
		wc_server = frappe.get_doc("WooCommerce Server", self.wc_server.name)
		wc_server.submit_sales_orders = 0
		wc_server.enable_payments_sync = 0
		wc_server.flags.ignore_mandatory = True
		wc_server.save()

		# Create a new order in WooCommerce
		wc_order_id = self.post_woocommerce_order(payment_method_title="Doge", item_price=10, item_qty=3)

		# Create an additional item in WooCommerce and in ERPNext, and link them
		wc_product_id = self.post_woocommerce_product(product_name="ADDITIONAL_ITEM", regular_price=20)
		# Create the same product in ERPNext and link it
		item = create_item(
			"ADDITIONAL_ITEM", valuation_rate=10, warehouse=None, company=get_default_company()
		)
		row = item.append("woocommerce_servers")
		row.woocommerce_id = wc_product_id
		row.woocommerce_server = get_woocommerce_server(self.wc_url).name
		item.save()

		# Run synchronisation for the ERPNext Sales Order to be created
		run_sales_orders_sync()

		# Expect no errors logged
		mock_log_error.assert_not_called()

		# Expect newly created Sales Order in ERPNext
		sales_order = frappe.get_doc("Sales Order", {"woocommerce_id": wc_order_id})
		self.assertIsNotNone(sales_order)

		# In ERPNext, change quantity of first item, and add an additional item
		sales_order.items[0].qty = 2
		sales_order.append(
			"items",
			{
				"item_code": item.name,
				"delivery_date": sales_order.delivery_date,
				"qty": 1,
				"rate": 20,
				"warehouse": "Stores - SC",
			},
		)
		sales_order.save()
		sales_order.submit()

		# Run synchronisation again, to sync the Sales Order changes
		run_sales_orders_sync(sales_order_name=sales_order.name)
		mock_log_error.assert_not_called()

		# Expect WooCommerce Order to have updated items
		wc_order = self.get_woocommerce_order(order_id=wc_order_id)
		wc_line_items = wc_order.get("line_items")
		self.assertEqual(wc_line_items[0].get("quantity"), 2)
		self.assertEqual(wc_line_items[1].get("name"), item.name)
		self.assertEqual(wc_line_items[1].get("quantity"), 1)
		self.assertEqual(get_tax_inc_price_for_woocommerce_line_item(wc_line_items[1]), 20)

		# Delete order in WooCommerce
		self.delete_woocommerce_order(wc_order_id=wc_order_id)

	def test_sync_creates_woocommerce_order_with_woo_id_when_synchronising_with_woocommerce(
		self, mock_log_error
	):
		"""
		Test that the Sales Order Synchornisation method creates a WooCommerce Order
		when only a WooCommerce Order ID is passed
		"""
		# Create a new order in WooCommerce
		wc_order_id = self.post_woocommerce_order()

		# Run synchronisation for the ERPNext Sales Order to be created
		run_sales_orders_sync(woocommerce_order_id=str(wc_order_id))

		# Expect no errors logged
		mock_log_error.assert_not_called()

		# Expect newly created Sales Order in ERPNext
		sales_order = frappe.get_doc("Sales Order", {"woocommerce_id": wc_order_id})
		self.assertIsNotNone(sales_order)

		# Delete order in WooCommerce
		self.delete_woocommerce_order(wc_order_id=wc_order_id)
