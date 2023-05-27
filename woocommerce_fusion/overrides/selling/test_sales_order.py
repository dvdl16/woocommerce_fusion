import json
from unittest.mock import Mock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from woocommerce_fusion.overrides.selling.sales_order import (
	get_woocommerce_order_shipment_trackings,
	update_woocommerce_order_shipment_trackings
)


@patch("woocommerce_fusion.overrides.selling.sales_order.get_woocommerce_order")
class TestWooCommerceOrder(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()  # important to call super() methods when extending TestCase.

	def test_get_woocommerce_order_shipment_trackings(self, mock_get_woocommerce_order):
		"""
		Test that the get_woocommerce_order_shipment_trackings method works as expected
		"""
		woocommerce_order = frappe._dict(shipment_trackings=json.dumps([{'foo': 'bar'}]))
		mock_get_woocommerce_order.return_value = woocommerce_order

		sales_order = frappe._dict(
			doctype="Sales Order",
			woocommerce_site="site1.example.com",
			woocommerce_id="1"
		)
		doc = json.dumps(sales_order)
		result = get_woocommerce_order_shipment_trackings(doc)
		
		self.assertEqual(result, [{'foo': 'bar'}])


	def test_update_woocommerce_order_shipment_trackings(self, mock_get_woocommerce_order):
		"""
		Test that the update_woocommerce_order_shipment_trackings method works as expected
		"""
		class DummyWooCommerceOrder():
			def __init__(self, shipment_trackings):
				self.shipment_trackings = shipment_trackings

			def save(self):
				pass

		woocommerce_order = DummyWooCommerceOrder(shipment_trackings=json.dumps([{'foo': 'bar'}]))
		mock_get_woocommerce_order.return_value = woocommerce_order

		new_shipment_trackings = [{'foo': 'baz'}]

		sales_order = frappe._dict(
			doctype="Sales Order",
			woocommerce_site="site1.example.com",
			woocommerce_id="1"
		)
		doc = json.dumps(sales_order)
		update_woocommerce_order_shipment_trackings(doc, new_shipment_trackings)

		updated_woocommerce_order = mock_get_woocommerce_order.return_value
		
		self.assertEqual(updated_woocommerce_order.shipment_trackings, [{'foo': 'baz'}])

