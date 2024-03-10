import base64
import hashlib
import hmac
import json

import frappe
from werkzeug.wrappers import Response

from woocommerce_fusion.tasks.sync_sales_orders import run_sales_orders_sync


def verify_request():
	woocommerce_settings = frappe.get_doc("Woocommerce Integration Settings")
	sig = base64.b64encode(
		hmac.new(
			woocommerce_settings.secret.encode("utf8"), frappe.request.data, hashlib.sha256
		).digest()
	)

	if (
		frappe.request.data
		and not sig == frappe.get_request_header("X-Wc-Webhook-Signature", "").encode()
	):
		return Response(status=401)

	frappe.set_user(woocommerce_settings.creation_user)


@frappe.whitelist(allow_guest=True)
def order_created(*args, **kwargs):
	"""
	Accepts payload data from WooCommerce "Order Created" webhook
	"""
	if frappe.request and frappe.request.data:
		verify_request()
		try:
			order = json.loads(frappe.request.data)
		except ValueError:
			# woocommerce returns 'webhook_id=value' for the first request which is not JSON
			order = frappe.request.data
		event = frappe.get_request_header("X-Wc-Webhook-Event")
	else:
		return Response(status=200)

	if event == "created":
		frappe.enqueue(run_sales_orders_sync, queue="long", woocommerce_order_id=order.get("id"))
		return Response(status=200)
