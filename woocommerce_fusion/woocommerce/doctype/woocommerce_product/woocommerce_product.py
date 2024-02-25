# Copyright (c) 2024, Dirk van der Laarse and contributors
# For license information, please see license.txt

from dataclasses import dataclass
from typing import Dict

from woocommerce_fusion.woocommerce.woocommerce_api import WooCommerceAPI, WooCommerceResource


@dataclass
class WooCommerceProductAPI(WooCommerceAPI):
	"""Class for keeping track of a WooCommerce site."""

	pass


class WooCommerceProduct(WooCommerceResource):
	"""
	Virtual doctype for WooCommerce Products
	"""

	resource: str = "products"
	field_setter_map = {"woocommerce_name": "name", "woocommerce_id": "id"}

	# use "args" despite frappe-semgrep-rules.rules.overusing-args, following convention in ERPNext
	# nosemgrep
	@staticmethod
	def get_list(args):
		return WooCommerceProduct.get_list_of_records(args)

	def after_load_from_db(self, product: Dict):
		product.pop("name")
		product = self.set_title(product)
		return product

	@classmethod
	def during_get_list_of_records(cls, product: Dict):
		product = cls.set_title(product)
		return product

	@staticmethod
	def set_title(product: str):
		product[
			"title"
		] = f"{(product['sku'] + ' - ') if product['sku'] else ''}{product['woocommerce_name']}"
		return product

	# use "args" despite frappe-semgrep-rules.rules.overusing-args, following convention in ERPNext
	# nosemgrep
	@staticmethod
	def get_count(args) -> int:
		return WooCommerceProduct.get_count_of_records(args)

	def before_db_insert(self, product: Dict):
		return self.clean_up_product(product)

	def before_db_update(self, product: Dict):
		return self.clean_up_product(product)

	def after_db_update(self):
		pass

	@staticmethod
	def clean_up_product(product):
		"""
		Perform some tasks to make sure that an product is in the correct format for the WC API
		"""

		# Convert back to string
		product["weight"] = str(product["weight"])
		product["regular_price"] = str(product["regular_price"])

		# Do not post Sale Price if it is 0
		if product["sale_price"] and product["sale_price"] > 0:
			product["sale_price"] = str(product["sale_price"])
		else:
			product.pop("sale_price")

		# Set corrected properties
		product["name"] = str(product["woocommerce_name"])

		# Remove the read-only `display_value` and `display_key` attributes as per
		# https://github.com/woocommerce/woocommerce/issues/32038#issuecomment-1117140390
		# This avoids HTTP 400 errors when updating orders, e.g. "line_items[0][meta_data][0][display_value] is not of type string"
		# if "line_items" in order and order["line_items"]:
		# 	for line in order["line_items"]:
		# 		if "meta_data" in line:
		# 			for meta in line["meta_data"]:
		# 				if "display_key" in meta:
		# 					meta.pop("display_key")
		# 				if "display_value" in meta:
		# 					meta.pop("display_value")

		return product
