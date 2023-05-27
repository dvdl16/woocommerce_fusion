frappe.ui.form.on('Item', {
	refresh: function(frm) {
		// Add a custom button to sync Item with WooCommerce
		frm.add_custom_button(__("Sync this Item to WooCommerce"), function () {
			frm.trigger("sync_item");
		}, __('Actions'));
	},

	sync_item: function(frm) {
		// Sync this Item
		frappe.call({
			method: "woocommerce_fusion.tasks.stock_update.update_stock_levels_on_woocommerce_site",
			args: {
				item_code: frm.doc.name
			},
			callback: function(r) {
				if (r.message === true){
					frappe.show_alert({
						indicator: "green",
						message: __("Syncrhonised stock levels to WooCommerce"),
					});
				}
				else {
					frappe.show_alert({
						indicator: "red",
						message: __("Failed to syncrhonise stock levels to WooCommerce"),
					});
				}
			}
		});
	},
})
