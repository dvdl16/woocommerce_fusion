import frappe
import requests


def log_woocommerce_request(
	url: str,
	endpoint: str,
	request_method: str,
	params: dict,
	data: dict,
	res: requests.Response | None = None,
):
	request_log = frappe.get_doc(
		{
			"doctype": "WooCommerce Request Log",
			"user": frappe.session.user if frappe.session.user else None,
			"url": url,
			"endpoint": endpoint,
			"method": request_method,
			"params": frappe.as_json(params) if params else None,
			"data": frappe.as_json(data) if data else None,
			"response": f"{str(res)}\n{res.text}" if res is not None else None,
			"error": frappe.get_traceback(),
			"status": "Success" if res and res.status_code == 200 else "Error",
		}
	)

	request_log.save(ignore_permissions=True)
