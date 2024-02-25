app_name = "woocommerce_fusion"
app_title = "WooCommerce Fusion"
app_publisher = "Dirk van der Laarse"
app_description = "WooCommerce connector for ERPNext v14+"
app_email = "dirk@finfoot.work"
app_license = "GNU GPLv3"

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/woocommerce_fusion/css/woocommerce_fusion.css"
# app_include_js = "/assets/woocommerce_fusion/js/woocommerce_fusion.js"

# include js, css files in header of web template
# web_include_css = "/assets/woocommerce_fusion/css/woocommerce_fusion.css"
# web_include_js = "/assets/woocommerce_fusion/js/woocommerce_fusion.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "woocommerce_fusion/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {"Sales Order": "public/js/selling/sales_order.js", "Item": "public/js/stock/item.js"}
doctype_list_js = {"Sales Order": "public/js/selling/sales_order_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "woocommerce_fusion.utils.jinja_methods",
# 	"filters": "woocommerce_fusion.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "woocommerce_fusion.install.before_install"
# after_install = "woocommerce_fusion.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "woocommerce_fusion.uninstall.before_uninstall"
# after_uninstall = "woocommerce_fusion.uninstall.after_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "woocommerce_fusion.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

override_doctype_class = {
	"Sales Order": "woocommerce_fusion.overrides.selling.sales_order.CustomSalesOrder",
}

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }
doc_events = {
	"Stock Entry": {
		"on_submit": "woocommerce_fusion.tasks.stock_update.update_stock_levels_for_woocommerce_item",
		"on_cancel": "woocommerce_fusion.tasks.stock_update.update_stock_levels_for_woocommerce_item",
	},
	"Stock Reconciliation": {
		"on_submit": "woocommerce_fusion.tasks.stock_update.update_stock_levels_for_woocommerce_item",
		"on_cancel": "woocommerce_fusion.tasks.stock_update.update_stock_levels_for_woocommerce_item",
	},
	"Sales Invoice": {
		"on_submit": "woocommerce_fusion.tasks.stock_update.update_stock_levels_for_woocommerce_item",
		"on_cancel": "woocommerce_fusion.tasks.stock_update.update_stock_levels_for_woocommerce_item",
	},
	"Delivery Note": {
		"on_submit": "woocommerce_fusion.tasks.stock_update.update_stock_levels_for_woocommerce_item",
		"on_cancel": "woocommerce_fusion.tasks.stock_update.update_stock_levels_for_woocommerce_item",
	},
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	# 	"all": [
	# 		"woocommerce_fusion.tasks.all"
	# 	],
	# 	"weekly": [
	# 		"woocommerce_fusion.tasks.daily"
	# 	],
	"hourly": ["woocommerce_fusion.tasks.sync_sales_orders.run_sales_orders_sync"],
	"daily": [
		"woocommerce_fusion.tasks.stock_update.update_stock_levels_for_all_enabled_items_in_background"
	],
	# 	"monthly": [
	# 		"woocommerce_fusion.tasks.monthly"
	# 	],
}

# Testing
# -------

before_tests = "woocommerce_fusion.setup.utils.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "woocommerce_fusion.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

ignore_links_on_delete = [
	"WooCommerce Request Log",
]

# Request Events
# ----------------
# before_request = ["woocommerce_fusion.utils.before_request"]
# after_request = ["woocommerce_fusion.utils.after_request"]

# Job Events
# ----------
# before_job = ["woocommerce_fusion.utils.before_job"]
# after_job = ["woocommerce_fusion.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"woocommerce_fusion.auth.validate"
# ]


fixtures = [
	{
		"dt": "Custom Field",
		"filters": [
			[
				"name",
				"in",
				(
					"Customer-woocommerce_server",
					"Customer-woocommerce_email",
					"Sales Order-woocommerce_id",
					"Sales Order-woocommerce_server",
					"Sales Order-woocommerce_status",
					"Sales Order-woocommerce_payment_method",
					"Sales Order-woocommerce_shipment_tracking_html",
					"Sales Order-woocommerce_payment_entry",
					"Address-woocommerce_server",
					"Address-woocommerce_email",
					"Item-woocommerce_servers",
				),
			]
		],
	}
]
