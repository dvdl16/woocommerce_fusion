from frappe.exceptions import ValidationError


class SyncDisabledError(ValidationError):
	pass
