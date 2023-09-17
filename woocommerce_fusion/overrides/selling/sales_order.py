import json

import frappe
from frappe import _

from woocommerce_fusion.woocommerce.doctype.woocommerce_order.woocommerce_order import (
	generate_woocommerce_order_name_from_domain_and_id,
)


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
