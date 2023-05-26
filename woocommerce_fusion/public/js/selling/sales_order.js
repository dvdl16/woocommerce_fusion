frappe.ui.form.on('Sales Order', {
	refresh: function(frm) {
		// Add a custom button to sync Sales Orders woth WooCommerce
		frm.add_custom_button(__("Sync this Order with WooCommerce"), function () {
			frm.trigger("sync_sales_order");
		}, __('Actions'));
	},

	sync_sales_order: function(frm) {
		// Sync this Sales Order
		frappe.call({
			method: "woocommerce_fusion.tasks.sync.sync_sales_orders",
			args: {
				sales_order_name: frm.doc.name
			},
			callback: function(r) {
				frm.reload_doc();
			}
		});
	},

	woocommerce_status: function(frm) {
		// Triggered when woocommerce_status is changed
		frappe.confirm(
			'Changing the status will update the order status on WooCommerce. Do you want to continue?',
			function(){
				frm.save('Update', function(){
					// Sync
					frappe.call({
						method: "woocommerce_fusion.tasks.sync.sync_sales_orders",
						args: {
							sales_order_name: frm.doc.name
						},
						callback: function(r) {
							if(r.message) {
								debugger
							}
						}
					});
				})
			},
			function(){
				frm.reload_doc();
			}
		);
	}
});
