// Copyright (c) 2023, Dirk van der Laarse and contributors
// For license information, please see license.txt

frappe.ui.form.on('WooCommerce Server', {
	refresh: function(frm) {
		// Only list enabled warehouses
		frm.fields_dict.warehouses.get_query = function (doc) {
			return {
				filters: {
					disabled: 0,
					is_group: 0
				}
			};
		}
	},
	// View WooCommerce Webhook Configuration
	view_webhook_config: function(frm) {
		let d = new frappe.ui.Dialog({
			title: __('WooCommerce Webhook Settings'),
			fields: [
				{
					label: __('Status'),
					fieldname: 'status',
					fieldtype: 'Data',
					default: 'Active',
					read_only: 1
				},
				{
					label: __('Topic'),
					fieldname: 'topic',
					fieldtype: 'Data',
					default: 'Order created',
					read_only: 1
				},
				{
					label: __('Delivery URL'),
					fieldname: 'url',
					fieldtype: 'Data',
					default: '<site url here>/api/method/woocommerce_fusion.woocommerce_endpoint.order_created',
					read_only: 1
				},
				{
					label: __('Secret'),
					fieldname: 'secret',
					fieldtype: 'Code',
					default: frm.doc.secret,
					read_only: 1
				},
				{
					label: __('API Version'),
					fieldname: 'api_version',
					fieldtype: 'Data',
					default: 'WP REST API Integration v3',
					read_only: 1
				}
			],
			size: 'large', // small, large, extra-large
			primary_action_label: __('OK'),
			primary_action(values) {
				d.hide();
			}
		});

		d.show();

	}
});
