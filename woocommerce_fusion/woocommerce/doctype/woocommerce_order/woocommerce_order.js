// Copyright (c) 2023, Dirk van der Laarse and contributors
// For license information, please see license.txt

frappe.ui.form.on('WooCommerce Order', {
	refresh: function(frm) {
		// Add a custom button to sync this WooCommerce order to a Sales Order
		frm.add_custom_button(__("Sync this Order to ERPNext"), function () {
			frm.trigger("sync_sales_order");
		}, __('Actions'));
	},
	sync_sales_order: function(frm) {
		// Sync this WooCommerce Order
		frappe.call({
			method: "woocommerce_fusion.tasks.sync_sales_orders.run_sales_orders_sync",
			args: {
				// woocommerce_order_id: frm.doc.id
			},
			callback: function(r) {
				frm.reload_doc();
			}
		});
	},
});
