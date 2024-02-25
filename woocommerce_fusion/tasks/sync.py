import base64
import hashlib
import hmac
from typing import Optional

import frappe
from frappe import _, _dict

from woocommerce_fusion.woocommerce.doctype.woocommerce_integration_settings.woocommerce_integration_settings import (
	WooCommerceIntegrationSettings,
)


class SynchroniseWooCommerce:
	"""
	Class for managing synchronisation of WooCommerce data with ERPNext data
	"""

	settings: WooCommerceIntegrationSettings | _dict

	def __init__(self, settings: Optional[WooCommerceIntegrationSettings | _dict] = None) -> None:
		self.settings = settings if settings else frappe.get_single("WooCommerce Integration Settings")


def log_and_raise_error(err):
	"""
	Create an "Error Log" and raise error
	"""
	log = frappe.log_error("WooCommerce Error", err)
	log_link = frappe.utils.get_link_to_form("Error Log", log.name)
	frappe.throw(
		msg=_("Something went wrong while connecting to WooCommerce. See Error Log {0}").format(
			log_link
		),
		title=_("WooCommerce Error"),
	)
	raise err


def verify_request():
	woocommerce_integration_settings = frappe.get_doc("WooCommerce Integration Settings")
	sig = base64.b64encode(
		hmac.new(
			woocommerce_integration_settings.secret.encode("utf8"), frappe.request.data, hashlib.sha256
		).digest()
	)

	if (
		frappe.request.data
		and not sig == frappe.get_request_header("X-Wc-Webhook-Signature", "").encode()
	):
		frappe.throw(_("Unverified Webhook Data"))
	frappe.set_user(woocommerce_integration_settings.creation_user)
