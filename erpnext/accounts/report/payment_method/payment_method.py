# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.utils import getdate
from erpnext import get_company_currency

def execute(filters=None):
	if not filters:
		return [], []

	if not filters.get("company"):
		frappe.throw(_("Company is mandatory"))

	if not filters.get("from_date") and not filters.get("to_date"):
		frappe.throw(
			_("{0} and {1} are mandatory").format(frappe.bold(_("From Date")), frappe.bold(_("To Date")))
		)

	if filters.get("from_date") and filters.get("to_date") and getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date must be before To Date"))

	# Get company currency
	company_currency = get_company_currency(filters.company)

	# Define columns
	columns = [
		{
			"label": _("Posting Date"),
			"fieldname": "posting_date",
			"fieldtype": "Date",
			"width": 100
		},
		{
			"label": _("Payment Method"),
			"fieldname": "payment_method",
			"fieldtype": "Data",
			"width": 200
		},
		{
			"label": _("Total Amount ({0})").format(company_currency),
			"fieldname": "total_amount",
			"fieldtype": "Currency",
			"width": 180
		},
		{
			"label": _("Transaction Count"),
			"fieldname": "transaction_count",
			"fieldtype": "Data",
			"width": 140
		},
		{
			"label": _("View GL"),
			"fieldname": "gl_link",
			"fieldtype": "Button",
			"width": 80
		},
	]

	# Konversi tanggal ke format yang benar
	from_date = getdate(filters.get('from_date'))
	to_date = getdate(filters.get('to_date'))

	# Query to get payment entries grouped by date and payment_method
	sql_query = """
		SELECT
			pe.posting_date,
			IFNULL(pe.payment_method, 'Not Specified') as payment_method,
			SUM(pe.paid_amount) as total_amount,
			COUNT(pe.name) as transaction_count
		FROM `tabPayment Entry` pe
		WHERE pe.docstatus = 1
			AND pe.company = %(company)s
			AND pe.posting_date BETWEEN %(from_date)s AND %(to_date)s
	"""

	# Add branch filter if specified
	if filters.get('branch'):
		sql_query += " AND pe.payment_branch = %(branch)s"

	# Add grouping and ordering
	sql_query += """
		GROUP BY pe.posting_date, payment_method
		ORDER BY pe.posting_date, total_amount DESC
	"""

	# Prepare query parameters
	query_params = {
		'company': filters.get('company'),
		'from_date': from_date,
		'to_date': to_date
	}

	# Add branch parameter if specified
	if filters.get('branch'):
		query_params['branch'] = filters.get('branch')

	# Execute query
	payment_entries = frappe.db.sql(sql_query, query_params, as_dict=1)

	# Calculate subtotals by date
	result = []
	current_date = None
	date_total_amount = 0
	date_total_count = 0

	for entry in payment_entries:
		if current_date != entry.posting_date:
			# Add subtotal row for previous date
			if current_date:
				# Create GL link URL for subtotal
				gl_url = f"/app/query-report/General Ledger?company={filters.get('company')}&from_date={current_date}&to_date={current_date}&voucher_type=Payment Entry&debit_greater_than=0.001"
				if filters.get('branch'):
					gl_url += f"&branch={filters.get('branch')}"

				result.append({
					"posting_date": current_date,
					"payment_method": "<b>Subtotal</b>",
					"total_amount": date_total_amount,
					"transaction_count": date_total_count,
					"gl_link": f"<a href='{gl_url}' target='_blank'>View GL</a>",
					"is_subtotal": True
				})

			# Reset for new date
			current_date = entry.posting_date
			date_total_amount = 0
			date_total_count = 0

		# Create GL link URL
		gl_url = f"/app/query-report/General Ledger?company={filters.get('company')}&from_date={entry.posting_date}&to_date={entry.posting_date}&voucher_type=Payment Entry&payment_method={entry.payment_method}&debit_greater_than=0.001"
		if filters.get('branch'):
			gl_url += f"&branch={filters.get('branch')}"

		# Add GL link
		entry["gl_link"] = f"<a href='{gl_url}' target='_blank'>View GL</a>"
		result.append(entry)

		# Update date totals
		date_total_amount += entry.total_amount
		date_total_count += entry.transaction_count

	# Add subtotal for the last date
	if current_date:
		# Create GL link URL for last subtotal
		gl_url = f"/app/query-report/General Ledger?company={filters.get('company')}&from_date={current_date}&to_date={current_date}&voucher_type=Payment Entry&debit_greater_than=0.001"
		if filters.get('branch'):
			gl_url += f"&branch={filters.get('branch')}"

		result.append({
			"posting_date": current_date,
			"payment_method": "<b>Subtotal</b>",
			"total_amount": date_total_amount,
			"transaction_count": date_total_count,
			"gl_link": f"<a href='{gl_url}' target='_blank'>View GL</a>",
			"is_subtotal": True
		})

	# Calculate grand total
	grand_total_amount = sum(entry.total_amount for entry in payment_entries)
	grand_total_count = sum(entry.transaction_count for entry in payment_entries)

	# Add grand total row
	if result:
		# Create GL link URL for grand total
		gl_url = f"/app/query-report/General Ledger?company={filters.get('company')}&from_date={filters.get('from_date')}&to_date={filters.get('to_date')}&voucher_type=Payment Entry&debit_greater_than=0.001"
		if filters.get('branch'):
			gl_url += f"&branch={filters.get('branch')}"

		result.append({
			"posting_date": "",
			"payment_method": "<b>Grand Total</b>",
			"total_amount": grand_total_amount,
			"transaction_count": grand_total_count,
			"gl_link": f"<a href='{gl_url}' target='_blank'>View GL</a>"
		})

	return columns, result
