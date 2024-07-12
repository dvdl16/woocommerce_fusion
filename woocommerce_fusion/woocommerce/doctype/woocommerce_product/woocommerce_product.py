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

	doctype = "WooCommerce Product"
	resource: str = "products"
	child_resource: str = "variations"
	field_setter_map = {"woocommerce_name": "name", "woocommerce_id": "id"}

	# use "args" despite frappe-semgrep-rules.rules.overusing-args, following convention in ERPNext
	# nosemgrep
	@staticmethod
	def get_list(args):
		products = WooCommerceProduct.get_list_of_records(args)

		# Extend the list with product variants
		product_ids_with_variants = [
			product.get("id") for product in products if product.get("type") == "variable"
		]
		for id in product_ids_with_variants:
			args["endpoint"] = f"products/{id}/variations"
			variants = WooCommerceProduct.get_list_of_records(args)
			products.extend(variants)

		return products

	def after_load_from_db(self, product: Dict):
		product.pop("name")
		product = self.set_title(product)
		return product

	@classmethod
	def during_get_list_of_records(cls, product: Dict):
		product = cls.set_title(product)
		return product

	@staticmethod
	def set_title(product: dict):
		# Variations won't have the woocommerce_name property
		if wc_name := product.get("woocommerce_name"):
			if sku := product.get("sku"):
				product["title"] = f"{sku} - {wc_name}"
			else:
				product["title"] = wc_name
		else:
			product["title"] = product["woocommerce_id"]

		return product

	# use "args" despite frappe-semgrep-rules.rules.overusing-args, following convention in ERPNext
	# nosemgrep
	@staticmethod
	def get_count(args) -> int:
		return WooCommerceProduct.get_count_of_records(args)

	def before_db_insert(self, product: Dict):
		return self.clean_up_product_before_write(product)

	def before_db_update(self, product: Dict):
		return self.clean_up_product_before_write(product)

	def after_db_update(self):
		pass

	@staticmethod
	def clean_up_product_before_write(product):
		"""
		Perform some tasks to make sure that an product is in the correct format for the WC API
		"""

		# Convert back to string
		product["weight"] = str(product["weight"])
		product["regular_price"] = str(product["regular_price"])

		# Do not post Sale Price if it is 0
		if product["sale_price"] and float(product["sale_price"]) > 0:
			product["sale_price"] = str(product["sale_price"])
		else:
			product.pop("sale_price")

		# Set corrected properties
		product["name"] = str(product["woocommerce_name"])

		# Drop 'related_ids' field
		product.pop("related_ids")

		return product
