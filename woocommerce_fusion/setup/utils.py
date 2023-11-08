import frappe
from erpnext.setup.utils import _enable_all_roles_for_admin, set_defaults_for_tests
from frappe.utils.data import now_datetime


def before_tests():
	frappe.clear_cache()
	# complete setup if missing
	from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

	if not frappe.db.a_row_exists("Company"):
		current_year = now_datetime().year
		setup_complete(
			{
				"currency": "INR",
				"full_name": "Test User",
				"company_name": "Some Company (Pty) Ltd",
				"timezone": "Africa/Johannesburg",
				"company_abbr": "SC",
				"industry": "Manufacturing",
				"country": "South Africa",
				"fy_start_date": f"{current_year}-01-01",
				"fy_end_date": f"{current_year}-12-31",
				"language": "english",
				"company_tagline": "Testing",
				"email": "test@erpnext.com",
				"password": "test",
				"chart_of_accounts": "Standard",
			}
		)

	_enable_all_roles_for_admin()

	set_defaults_for_tests()

	# following same practice as in erpnext app to commit manually inside before_tests
	# nosemgrep
	frappe.db.commit()
