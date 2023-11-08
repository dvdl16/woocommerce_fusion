import json

import frappe
from erpnext.selling.doctype.sales_order.sales_order import SalesOrder
from frappe import _
from frappe.model.naming import get_default_naming_series, make_autoname

from woocommerce_fusion.woocommerce.doctype.woocommerce_order.woocommerce_order import (
	generate_woocommerce_order_name_from_domain_and_id,
)


class CustomSalesOrder(SalesOrder):
	"""
	This class extends ERPNext's Sales Order doctype to override the autoname method

	This allows us to name the Sales Order conditionally.
	"""

	def autoname(self):
		"""
		If this is a WooCommerce-linked order, name should be WEB[WooCommerce Order ID], e.g. WEB012142
		else, name it normally.
		"""
		if self.woocommerce_id:
			# Get idx of site
			woocommerce_additional_settings = frappe.get_single("WooCommerce Additional Settings")
			wc_server = next(
				(
					server
					for server in woocommerce_additional_settings.servers
					if self.woocommerce_site in server.woocommerce_server_url
				),
				None,
			)
			idx = wc_server.idx if wc_server else 0
			self.name = "WEB{}-{:06}".format(
				idx, int(self.woocommerce_id)
			)  # Format with leading zeros to make it 6 digits
		else:
			naming_series = get_default_naming_series("Sales Order")
			self.name = make_autoname(key=naming_series)


@frappe.whitelist()
def get_woocommerce_order_shipment_trackings(doc):
	"""
	Fetches shipment tracking details from a WooCommerce order.
	"""
	doc = frappe._dict(json.loads(doc))
	if doc.woocommerce_site and doc.woocommerce_id:
		wc_order = get_woocommerce_order(doc.woocommerce_site, doc.woocommerce_id)
		if wc_order.shipment_trackings:
			return json.loads(wc_order.shipment_trackings)

	return []


@frappe.whitelist()
def update_woocommerce_order_shipment_trackings(doc, shipment_trackings):
	"""
	Updates the shipment tracking details of a specific WooCommerce order.
	"""
	doc = frappe._dict(json.loads(doc))
	if doc.woocommerce_site and doc.woocommerce_id:
		wc_order = get_woocommerce_order(doc.woocommerce_site, doc.woocommerce_id)
	wc_order.shipment_trackings = shipment_trackings
	wc_order.save()
	return wc_order.shipment_trackings


def get_woocommerce_order(woocommerce_site, woocommerce_id):
	"""
	Retrieves a specific WooCommerce order based on its site and ID.
	"""
	# First verify if the WooCommerce site exits, and it sync is enabled
	wc_order_name = generate_woocommerce_order_name_from_domain_and_id(
		woocommerce_site, woocommerce_id
	)
	wc_additional_settings = frappe.get_cached_doc("WooCommerce Additional Settings")
	wc_server = next(
		(
			server
			for server in wc_additional_settings.servers
			if woocommerce_site in server.woocommerce_server_url
		),
		None,
	)

	if not wc_server:
		frappe.throw(
			_(
				"This Sales Order is linked to WooCommerce site '{0}', but this site can not be found in 'WooCommerce Additional Settings'"
			).format(woocommerce_site)
		)

	if not wc_server.enable_sync:
		frappe.throw(
			_(
				"This Sales Order is linked to WooCommerce site '{0}', but Synchronisation for this site is disabled in 'WooCommerce Additional Settings'"
			).format(woocommerce_site)
		)

	wc_order = frappe.get_doc({"doctype": "WooCommerce Order", "name": wc_order_name})
	wc_order.load_from_db()
	return wc_order
