from erpnext.erpnext_integrations.doctype.woocommerce_settings.woocommerce_settings import (
	WoocommerceSettings,
)
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


class CustomWoocommerceSettings(WoocommerceSettings):
	"""
	This class extends ERPNext's WoocommerceSettings doctype to override the create_delete_custom_fields method

	This allows us to create additional custom fields.
	"""

	def create_delete_custom_fields(self):
		super().create_delete_custom_fields()
		if self.enable_sync:
			create_custom_fields(
				{
					("Customer", "Sales Order", "Item", "Address"): dict(
						fieldname="woocommerce_site",
						label="Woocommerce Site",
						fieldtype="Data",
						read_only=1,
						print_hide=1,
					),
					("Sales Order"): dict(
						fieldname="woocommerce_status",
						label="Woocommerce Status",
						fieldtype="Select",
						options="\nPending Payment\nOn hold\nFailed\nCancelled"
						"\nProcessing\nRefunded\nShipped\nReady for Pickup"
						"\nPicked up\nDelivered\nProcessing LP\nDraft\n",
						allow_on_submit=1,
					),
					("Item"): dict(
						fieldname="woocommerce_servers",
						label="",
						fieldtype="Table",
						options="Item WooCommerce Server",
					),
				}
			)
			create_custom_fields(
				{
					("Sales Order"): dict(
						fieldname="woocommerce_shipment_tracking_html", label="", fieldtype="HTML"
					),
				}
			)
