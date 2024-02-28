from typing import List, Optional

import frappe
from frappe import qb
from frappe.query_builder import Criterion

from woocommerce_fusion.tasks.sync import SynchroniseWooCommerce
from woocommerce_fusion.woocommerce.doctype.woocommerce_integration_settings.woocommerce_integration_settings import (
	WooCommerceIntegrationSettings,
)
from woocommerce_fusion.woocommerce.woocommerce_api import (
	generate_woocommerce_record_name_from_domain_and_id,
)


def update_item_price_for_woocommerce_item_from_hook(doc, method):
	if not frappe.flags.in_test:
		if doc.doctype == "Item Price":
			frappe.enqueue(
				"woocommerce_fusion.tasks.sync_item_prices.run_item_price_sync",
				enqueue_after_commit=True,
				item_code=doc.item_code,
				price_list_rate=doc.price_list_rate,
			)


@frappe.whitelist()
def run_item_price_sync_in_background():
	frappe.enqueue(run_item_price_sync, queue="long")


@frappe.whitelist()
def run_item_price_sync(item_code: Optional[str] = None, price_list_rate: Optional[float] = None):
	sync = SynchroniseItemPrice(item_code=item_code, price_list_rate=price_list_rate)
	sync.run()
	return True


class SynchroniseItemPrice(SynchroniseWooCommerce):
	"""
	Class for managing synchronisation of ERPNext Items with WooCommerce Products
	"""

	item_code: Optional[str]
	item_price_list: List

	def __init__(
		self,
		settings: Optional[WooCommerceIntegrationSettings | frappe._dict] = None,
		item_code: Optional[str] = None,
		price_list_rate: Optional[float] = None,
	) -> None:
		super().__init__(settings)
		self.item_code = item_code
		self.price_list_rate = price_list_rate
		self.wc_server = None
		self.item_price_list = []

	def run(self) -> None:
		"""
		Run synchornisation
		"""
		for server in self.settings.servers:
			self.wc_server = server
			self.get_erpnext_item_prices()
			self.sync_items_with_woocommerce_products()

	def get_erpnext_item_prices(self) -> None:
		"""
		Get list of ERPNext Item Prices to synchronise,
		"""
		if self.wc_server.enable_price_list_sync and self.wc_server.price_list:
			ip = qb.DocType("Item Price")
			iwc = qb.DocType("Item WooCommerce Server")
			and_conditions = []
			and_conditions.append(ip.price_list == self.wc_server.price_list)
			and_conditions.append(iwc.woocommerce_server == self.wc_server.woocommerce_server)
			if self.item_code:
				and_conditions.append(ip.item_code == self.item_code)

			self.item_price_list = (
				qb.from_(ip)
				.inner_join(iwc)
				.on(iwc.parent == ip.item_code)
				.select(ip.name, ip.item_code, ip.price_list_rate, iwc.woocommerce_server, iwc.woocommerce_id)
				.where(Criterion.all(and_conditions))
				.run(as_dict=True)
			)

	def sync_items_with_woocommerce_products(self) -> None:
		"""
		Synchronise Item Prices with WooCommerce Products
		"""
		for item_price in self.item_price_list:
			# Get the WooCommerce Product doc
			wc_product_name = generate_woocommerce_record_name_from_domain_and_id(
				domain=item_price.woocommerce_server, resource_id=item_price.woocommerce_id
			)
			wc_product = frappe.get_doc({"doctype": "WooCommerce Product", "name": wc_product_name})

			# try:
			wc_product.load_from_db()

			price_list_rate = self.price_list_rate or item_price.price_list_rate
			if wc_product.regular_price != price_list_rate:
				wc_product.regular_price = price_list_rate
				wc_product.save()
			# except Exception:
			# 	error_message = f"{frappe.get_traceback()}\n\n Order Data: \n{str(wc_order_data.as_dict())}"
			# 	frappe.log_error("WooCommerce Error: Price List Sync", error_message)
