# Copyright (c) 2023, Dirk van der Laarse and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document

from woocommerce_fusion.woocommerce.doctype.woocommerce_order.woocommerce_order import (
	parse_domain_from_url,
)


class WooCommerceServer(Document):
	def autoname(self):
		"""
		Derive name from woocommerce_server_url field
		"""
		self.name = parse_domain_from_url(self.woocommerce_server_url)
