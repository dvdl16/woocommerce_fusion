frappe.ui.form.on('Sales Order', {
	refresh: function(frm) {
		// Add a custom button to sync Sales Orders with WooCommerce
		if (frm.doc.woocommerce_id){
			frm.add_custom_button(__("Sync this Order with WooCommerce"), function () {
				frm.trigger("sync_sales_order");
			}, __('Actions'));
		}

		// Add a table with Shipment Trackings
		if (frm.doc.woocommerce_id && frm.doc.woocommerce_site){			
			frappe.call({
				method: "woocommerce_fusion.overrides.selling.sales_order.get_woocommerce_order_shipment_trackings",
				args: {
					doc: frm.doc
				},
				callback: function(r) {
					frappe.show_alert({
						indicator: "green",
						message: __("Retrieved WooCommerce Shipment Trackings"),
					});
					frm.doc.woocommerce_shipment_trackings = r.message;

					let trackingsHTML = `<b>WooCommerce Shipments:</b><br><table class="table table-striped">`+
					`<tr><th>Date Shipped</th><th>Provider</th><th>Tracking Number</th>`;
					frm.doc.woocommerce_shipment_trackings.forEach(tracking => {
						trackingsHTML += `<tr><td>${tracking.date_shipped}</td>`+
											`<td>${tracking.tracking_provider}</td>`+
											`<td><a href="${tracking.tracking_link}">${tracking.tracking_number}</a></td></tr>`
					});
					trackingsHTML += `</table>`
					frm.set_df_property('woocommerce_shipment_tracking_html', 'options', trackingsHTML);
					frm.refresh_field('woocommerce_shipment_tracking_html');
				}
			});
		}

		// Add a custom button to allow adding or editing Shipment Trackings
		if (frm.doc.woocommerce_id){
			frm.add_custom_button(__("Edit WooCommerce Shipment Trackings"), function () {
				frm.trigger("prompt_user_for_shipment_trackings");
			}, __('Actions'));
		}
	},

	sync_sales_order: function(frm) {
		// Sync this Sales Order
		frappe.call({
			method: "woocommerce_fusion.tasks.sync.sync_sales_orders",
			args: {
				sales_order_name: frm.doc.name,
				update_sync_date_in_settings: false
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
	},

	prompt_user_for_shipment_trackings: function(frm){
		//Get the shipment providers from 'WooCommerce Additional Settings'
		frappe.call({
			method: 
				"woocommerce_fusion.woocommerce.doctype.woocommerce_additional_settings"+
				".woocommerce_additional_settings.get_woocommerce_shipment_providers",
			args: {
				woocommerce_server_domain: frm.doc.woocommerce_site
			},
			callback: function(r) {
				const trackingProviders = r.message;
				let shipment_trackings = frm.doc.woocommerce_shipment_trackings

				
				//Prompt the use to update the Tracking Details
				let d = new frappe.ui.Dialog({
					title: __('Enter Shipment Tracking details'),
					fields: [
						{
							'fieldname': 'tracking_id',
							'fieldtype': 'Data',
							'label': 'Tracking ID',
							'read_only': 1,
							'default': shipment_trackings[0].tracking_id
						},
						{
							'fieldname': 'tracking_provider',
							'fieldtype': 'Select',
							'label': 'Tracking Provider',
							'reqd': 1,
							'options': trackingProviders,
							'default': shipment_trackings[0].tracking_provider
						},
						{
							'fieldname': 'tracking_number',
							'fieldtype': 'Data',
							'label': 'Tracking Number',
							'reqd': 1,
							'default': shipment_trackings[0].tracking_number
						},
						{
							'fieldname': 'tracking_link',
							'fieldtype': 'Data',
							'label': 'Tracking Link',
							'read_only': 1,
							'default': shipment_trackings[0].tracking_link
						},
						{
							'fieldname': 'date_shipped',
							'fieldtype': 'Date',
							'label': 'Date Shipped',
							'reqd': 1,
							'default': convert_ship_date_format_to_site_format(
								shipment_trackings[0].date_shipped
							)
						},
					],
					primary_action: function(){
						let values = d.get_values();
						let shipment_tracking = {
							"tracking_id": null,
							"tracking_provider": values.tracking_provider,
							"tracking_link": null,
							"tracking_number": values.tracking_number,
							"date_shipped": values.date_shipped
						};
						d.hide();

						// Call a method to update the shipment tracking
						frm.doc.woocommerce_shipment_trackings = [shipment_tracking]
						frm.trigger("update_shipment_trackings");
					},
					primary_action_label: __('Submit and Sync to WooCommerce')
				});
				d.show();
			}
		})
	},

	update_shipment_trackings: function(frm){
		//Call method to update the Shipment Trackings
		frappe.call({
			method: 
				"woocommerce_fusion.overrides.selling.sales_order.update_woocommerce_order_shipment_trackings",
			args: {
				doc: frm.doc,
				shipment_trackings: frm.doc.woocommerce_shipment_trackings
			},
			callback: function(r) {
				frm.reload_doc();
			}
		})

	}
	
});


function convert_ship_date_format_to_site_format(epochTime){
	// Create a new Date object from epoch time in seconds
	let dateObj = new Date(epochTime * 1000);

	// Format the date
	let year = dateObj.getFullYear();
	let month = dateObj.getMonth() + 1; // getMonth() is zero-based
	let day = dateObj.getDate();

	// Ensure it's two digits. For example, 1 becomes 01
	if (month < 10) month = '0' + month;
	if (day < 10) day = '0' + day;

	// Concatenate in YYY-MM-DD format
	let formattedDate = `${year}-${month}-${day}`;

	return formattedDate; // Outputs: 2023-05-26

}