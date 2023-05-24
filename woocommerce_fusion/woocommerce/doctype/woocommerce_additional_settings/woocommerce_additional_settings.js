// Copyright (c) 2023, Dirk van der Laarse and contributors
// For license information, please see license.txt

frappe.ui.form.on('WooCommerce Additional Settings', {
	refresh: function(frm) {
		// Add a custom button to get Server details from ERPNext 'WooCommerce Settings'
		frm.add_custom_button(__("Get Server from ERPNext 'WooCommerce Settings'"), function () {
			frm.trigger("get_wc_server_details");
		}, __('Get from'));
	},

	get_wc_server_details: function(frm) {
		// Fetch WooCommerce Settings
		frappe.db.get_doc("Woocommerce Settings", "Woocommerce Settings")
			.then((doc) => {
				let server = frm.add_child('servers');
				server.woocommerce_server_url = doc.woocommerce_server_url;
				server.api_consumer_key = doc.api_consumer_key;
				server.api_consumer_secret = doc.api_consumer_secret;
				frm.refresh_field('servers');
				frm.save();
			});
	}

});
