import frappe
import requests
from woocommerce import API


class APIWithRequestLogging(API):
	"""WooCommerce API with Request Logging."""

	def _API__request(self, method, endpoint, data, params=None, **kwargs):
		"""Override _request method to also create a 'WooCommerce Request Log'"""
		try:
			result = super()._API__request(method, endpoint, data, params, **kwargs)
			frappe.enqueue(
				"woocommerce_fusion.tasks.utils.log_woocommerce_request",
				url=self.url,
				endpoint=endpoint,
				request_method=method,
				params=params,
				data=data,
				res=result,
			)
			return result
		except Exception as e:
			frappe.enqueue(
				"woocommerce_fusion.tasks.utils.log_woocommerce_request",
				url=self.url,
				endpoint=endpoint,
				request_method=method,
				params=params,
				data=data,
				res=result,
			)
			raise e


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
