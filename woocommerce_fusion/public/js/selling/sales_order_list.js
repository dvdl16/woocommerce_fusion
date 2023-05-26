frappe.listview_settings['Sales Order'] = {
	add_fields: ["woocommerce_status"],
	get_indicator: function(doc) {
		return [__(doc.woocommerce_status), {
			'Pending Payment': 'orange',
			'On hold': 'grey',
			'Failed': 'yellow',
			'Cancelled': 'red',
			'Processing': 'pink',
			'Refunded': 'grey',
			'Shipped': 'light-blue',
			'Ready for Pickup': 'light-yellow',
			'Picked up': 'light-green',
			'Delivered': 'green',
			'Processing LP': 'purple',
			'Draft': 'grey'
		}[doc.woocommerce_status], "woocommerce_status,=," + doc.woocommerce_status];
	},
	has_indicator_for_draft: true,
};


