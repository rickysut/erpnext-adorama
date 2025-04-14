# Copyright (c) 2023, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate

def execute(filters=None):
	if not filters:
		return [], []

	validate_filters(filters)

	columns = get_columns(filters)
	data = get_data(filters)

	return columns, data

def validate_filters(filters):
	if not filters.get("company"):
		frappe.throw(_("Company is mandatory"))

	if not filters.get("from_date") and not filters.get("to_date"):
		frappe.throw(_("From Date and To Date are mandatory"))

	if filters.get("from_date") and filters.get("to_date") and \
		getdate(filters.get("from_date")) > getdate(filters.get("to_date")):
		frappe.throw(_("From Date must be before To Date"))

def get_columns(filters):
	columns = [
		{
			"label": _("Sales Code"),
			"fieldname": "sales_code",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"label": _("Sales Person Name"),
			"fieldname": "sales_person_name",
			"fieldtype": "Data",
			"width": 180
		},
		{
			"label": _("Penjualan Barang (B)"),
			"fieldname": "penjualan_barang",
			"fieldtype": "Currency",
			"width": 150
		},
		{
			"label": _("Penjualan Cuci Cetak (F)"),
			"fieldname": "penjualan_cuci_cetak",
			"fieldtype": "Currency",
			"width": 180
		},
		{
			"label": _("TOTAL PENJUALAN"),
			"fieldname": "total_penjualan",
			"fieldtype": "Currency",
			"width": 150
		}
	]

	# Division columns have been removed as requested

	return columns

def get_data(filters):
	# Get sales orders with items (for division F)
	orders_with_items = get_sales_orders_with_items(filters)

	# Get sales invoices with items (for division B)
	invoices_with_items = get_sales_invoices_with_items(filters)

	# Combine data from sales orders and sales invoices
	combined_data = orders_with_items + invoices_with_items

	# Group data by sales person
	data = group_by_sales_person(combined_data)

	# Add grand total row
	data = add_grand_total(data)

	return data

def get_sales_invoices_with_items(filters):
	# Base filters for sales invoices
	si_filters = {
		"company": filters.get("company"),
		"posting_date": ["between", [filters.get("from_date"), filters.get("to_date")]],
		"docstatus": 1
	}

	# Add branch filter if specified and not empty
	if filters.get("branch") and filters.get("branch").strip():
		si_filters["branch_id"] = filters.get("branch")

	# Build the SQL query with proper filters
	query = """
		SELECT name, posting_date
		FROM `tabSales Invoice`
		WHERE docstatus = 1
		AND DATE(posting_date) >= %(from_date)s
		AND DATE(posting_date) <= %(to_date)s
		AND company = %(company)s
	"""

	# Add branch filter if specified and not empty
	if filters.get("branch") and filters.get("branch").strip():
		query += " AND branch_id = %(branch)s"

	# Prepare query parameters with proper date formatting
	query_params = {
		"from_date": filters.get("from_date"),
		"to_date": filters.get("to_date"),
		"company": filters.get("company")
	}

	# Add branch to parameters if specified and not empty
	if filters.get("branch") and filters.get("branch").strip():
		query_params["branch"] = filters.get("branch")

	# Execute the query
	sales_invoices = frappe.db.sql(query, query_params, as_dict=1)

	result = []

	# For each sales invoice, get the sales team and items
	for si in sales_invoices:
		# Get sales team for this sales invoice
		try:
			sales_team = frappe.get_all(
				"Sales Team",
				filters={"parent": si.name, "parenttype": "Sales Invoice"},
				fields=["sales_person", "allocated_percentage"]
			)

			# If no sales team, create a default entry with 100% allocation to "N/A"
			if not sales_team:
				sales_team = [{
					"sales_person": "N/A",
					"allocated_percentage": 100.0
				}]
		except Exception:
			# Use 'N/A' as sales person if there's an error
			sales_team = [{
				"sales_person": "N/A",
				"allocated_percentage": 100.0
			}]

		# Get items for this sales invoice
		items = frappe.get_all(
			"Sales Invoice Item",
			filters={"parent": si.name},
			fields=["item_code", "item_name", "item_group", "amount"]
		)

		# Assign divisions to items based ONLY on item_division from Item table
		for item in items:
			item_code = item.get("item_code")

			# Initialize division to empty
			item["division"] = ""

			# Get division ONLY from item_division field in Item table
			if item_code:
				try:
					division = frappe.db.get_value("Item", item_code, "item_division")
					if division in ["B", "F"]:
						item["division"] = division
				except:
					pass

		# Skip if no items
		if not items:
			continue

		# Group items by division
		division_totals = {"B": 0, "F": 0}

		# Calculate division totals - ONLY count items with explicit division
		for item in items:
			division = item.get("division")
			amount = flt(item.get("amount"))

			# Only add to totals if division is explicitly set
			if division == "F":
				division_totals["F"] += amount
			elif division == "B":
				division_totals["B"] += amount

		# For each sales person in the team, create an entry
		for sp in sales_team:
			# Get sales person details
			try:
				# Handle dictionary or object
				sales_person_name = sp.get("sales_person") if isinstance(sp, dict) else sp.sales_person

				# Handle 'N/A' sales person
				if sales_person_name == "N/A":
					sales_person_doc = frappe._dict({
						"name": "N/A",
						"sales_person_name": "Not Assigned",
						"sales_code": "N/A"
					})
				else:
					sales_person_doc = frappe.get_doc("Sales Person", sales_person_name)
			except frappe.DoesNotExistError:
				# Use 'N/A' if sales person doesn't exist
				sales_person_doc = frappe._dict({
					"name": "N/A",
					"sales_person_name": "Not Assigned",
					"sales_code": "N/A"
				})

			# Use full amount regardless of allocated_percentage
			penjualan_barang = flt(division_totals.get("B", 0))
			penjualan_cuci_cetak = flt(division_totals.get("F", 0))

			# Other divisions have been removed as requested
			other_divisions = {}

			# Get sales_code from the Sales Person DocType
			sales_code = ""
			if hasattr(sales_person_doc, "sales_code") and sales_person_doc.sales_code:
				sales_code = sales_person_doc.sales_code
			elif hasattr(sales_person_doc, "employee") and sales_person_doc.employee:
				# Try to get employee code
				try:
					employee = frappe.get_doc("Employee", sales_person_doc.employee)
					if employee and employee.employee_id:
						sales_code = employee.employee_id
				except:
					pass

			# If still no code, use first 5 chars of name
			if not sales_code and sales_person_doc.name:
				sales_code = sales_person_doc.name[:5]

			result_entry = {
				"sales_code": sales_code,
				"sales_person": sales_person_name,
				"sales_person_name": sales_person_doc.sales_person_name,
				"penjualan_barang": penjualan_barang,
				"penjualan_cuci_cetak": penjualan_cuci_cetak,
				"transaction_date": si.posting_date,
				"sales_invoice": si.name
			}

			# Add other divisions to the result
			for div_code, amount in other_divisions.items():
				result_entry[f"division_{div_code}"] = amount

			result.append(result_entry)

	return result

def get_sales_orders_with_items(filters):
	# Base filters for sales orders
	so_filters = {
		"company": filters.get("company"),
		"transaction_date": ["between", [filters.get("from_date"), filters.get("to_date")]],
		"docstatus": 1
	}

	# Add branch filter if specified and not empty
	if filters.get("branch") and filters.get("branch").strip():
		so_filters["order_branch"] = filters.get("branch")

	# Build the SQL query with proper filters - COMPLETELY NEW QUERY
	query = """
		SELECT name, transaction_date
		FROM `tabSales Order`
		WHERE docstatus = 1
		AND DATE(transaction_date) >= %(from_date)s
		AND DATE(transaction_date) <= %(to_date)s
		AND company = %(company)s
	"""

	# Add branch filter if specified and not empty
	if filters.get("branch") and filters.get("branch").strip():
		query += " AND order_branch = %(branch)s"

	# Prepare query parameters with proper date formatting
	query_params = {
		"from_date": filters.get("from_date"),
		"to_date": filters.get("to_date"),
		"company": filters.get("company")
	}

	# Process filters without logging

	# Add branch to parameters if specified and not empty
	if filters.get("branch") and filters.get("branch").strip():
		query_params["branch"] = filters.get("branch")

	# Execute query without logging

	# Execute the query
	sales_orders = frappe.db.sql(query, query_params, as_dict=1)

	# Process results without logging

	# Continue even if no sales orders found

	result = []

	# For each sales order, get the sales team and items
	for so in sales_orders:
		# Get sales team for this sales order
		try:
			sales_team = frappe.get_all(
				"Sales Team",
				filters={"parent": so.name, "parenttype": "Sales Order"},
				fields=["sales_person", "allocated_percentage"]
			)

			# If no sales team, create a default entry with 100% allocation to "Not Assigned"
			if not sales_team:
				# Try to find a sales person to use as default
				default_sales_persons = frappe.get_all("Sales Person", limit=1)
				if default_sales_persons:
					default_sales_person = default_sales_persons[0].name
					sales_team = [{
						"sales_person": default_sales_person,
						"allocated_percentage": 100.0
					}]
				else:
					# Use 'N/A' as sales person if no sales person exists
					sales_team = [{
						"sales_person": "N/A",
						"allocated_percentage": 100.0
					}]
		except Exception:
			# Use 'N/A' as sales person if there's an error
			sales_team = [{
				"sales_person": "N/A",
				"allocated_percentage": 100.0
			}]

		# Get items for this sales order with item_group
		items = frappe.get_all(
			"Sales Order Item",
			filters={"parent": so.name},
			fields=["item_code", "item_name", "item_group", "amount"]
		)

		# Assign divisions to items based ONLY on item_division from Item table
		for item in items:
			item_code = item.get("item_code")

			# Initialize division to empty
			item["division"] = ""

			# Get division ONLY from item_division field in Item table
			if item_code:
				try:
					division = frappe.db.get_value("Item", item_code, "item_division")
					if division in ["B", "F"]:
						item["division"] = division
				except:
					pass

			# If no division found, default to empty (will be excluded from both categories)
			# We don't use item_name or item_group to determine division

		# Skip if no items
		if not items:
			continue

		# Group items by division
		division_totals = {"B": 0, "F": 0}

		# Calculate division totals - ONLY count items with explicit division
		for item in items:
			division = item.get("division")
			amount = flt(item.get("amount"))

			# Only add to totals if division is explicitly set
			if division == "F":
				division_totals["F"] += amount
			elif division == "B":
				division_totals["B"] += amount
			# Items without division are not counted in either category

		# For each sales person in the team, create an entry
		for sp in sales_team:
			# Get sales person details
			try:
				# Handle dictionary or object
				sales_person_name = sp.get("sales_person") if isinstance(sp, dict) else sp.sales_person

				# Handle 'N/A' sales person
				if sales_person_name == "N/A":
					sales_person_doc = frappe._dict({
						"name": "N/A",
						"sales_person_name": "Not Assigned",
						"sales_code": "N/A"
					})
				else:
					sales_person_doc = frappe.get_doc("Sales Person", sales_person_name)
			except frappe.DoesNotExistError:
				# Use 'N/A' if sales person doesn't exist
				sales_person_doc = frappe._dict({
					"name": "N/A",
					"sales_person_name": "Not Assigned",
					"sales_code": "N/A"
				})

			# Use full amount regardless of allocated_percentage
			penjualan_barang = flt(division_totals.get("B", 0))
			penjualan_cuci_cetak = flt(division_totals.get("F", 0))

			# Other divisions have been removed as requested
			other_divisions = {}

			# Always add the entry, even if sales are zero
			# This ensures that sales persons are shown in the report even if they have no sales

			# Get sales_code from the Sales Person DocType
			sales_code = ""
			if hasattr(sales_person_doc, "sales_code") and sales_person_doc.sales_code:
				sales_code = sales_person_doc.sales_code
			elif hasattr(sales_person_doc, "employee") and sales_person_doc.employee:
				# Try to get employee code
				try:
					employee = frappe.get_doc("Employee", sales_person_doc.employee)
					if employee and employee.employee_id:
						sales_code = employee.employee_id
				except:
					pass

			# If still no code, use first 5 chars of name
			if not sales_code and sales_person_doc.name:
				sales_code = sales_person_doc.name[:5]

			result_entry = {
				"sales_code": sales_code,
				"sales_person": sales_person_name,
				"sales_person_name": sales_person_doc.sales_person_name,
				"penjualan_barang": penjualan_barang,
				"penjualan_cuci_cetak": penjualan_cuci_cetak,
				"transaction_date": so.transaction_date,
				"sales_order": so.name
			}

			# Add other divisions to the result
			for div_code, amount in other_divisions.items():
				result_entry[f"division_{div_code}"] = amount

			result.append(result_entry)

	return result

def group_by_sales_person(orders_with_items):
	# Group by sales person
	sales_person_summary = {}

	for row in orders_with_items:
		sales_person = row.get("sales_person")

		if sales_person not in sales_person_summary:
			# Initialize with standard fields
			summary_entry = {
				"sales_code": row.get("sales_code"),
				"sales_person_name": row.get("sales_person_name"),
				"penjualan_barang": 0,
				"penjualan_cuci_cetak": 0,
				"total_penjualan": 0
			}

			# Division fields have been removed as requested

			sales_person_summary[sales_person] = summary_entry

		sales_person_summary[sales_person]["penjualan_barang"] += flt(row.get("penjualan_barang"))
		sales_person_summary[sales_person]["penjualan_cuci_cetak"] += flt(row.get("penjualan_cuci_cetak"))

		# Calculate total penjualan
		sales_person_summary[sales_person]["total_penjualan"] = flt(sales_person_summary[sales_person]["penjualan_barang"]) + flt(sales_person_summary[sales_person]["penjualan_cuci_cetak"])

		# Division fields have been removed as requested

	# Convert to list
	result = []
	for sales_person, summary in sales_person_summary.items():
		entry = {
			"sales_code": summary.get("sales_code", ""),
			"sales_person_name": summary["sales_person_name"],
			"penjualan_barang": summary["penjualan_barang"],
			"penjualan_cuci_cetak": summary["penjualan_cuci_cetak"],
			"total_penjualan": summary["total_penjualan"]
		}

		# Division fields have been removed as requested

		result.append(entry)

	# Sort by sales person name
	result = sorted(result, key=lambda x: x.get("sales_person_name") or "")

	return result

def add_grand_total(data):
	# Calculate grand totals
	total_penjualan_barang = sum(row.get("penjualan_barang") for row in data)
	total_penjualan_cuci_cetak = sum(row.get("penjualan_cuci_cetak") for row in data)
	total_penjualan = sum(row.get("total_penjualan") for row in data)

	# Division totals have been removed as requested
	division_totals = {}

	# Add grand total row
	if data:
		grand_total_row = {
			"sales_code": "",
			"sales_person_name": "<b>Grand Total</b>",
			"penjualan_barang": total_penjualan_barang,
			"penjualan_cuci_cetak": total_penjualan_cuci_cetak,
			"total_penjualan": total_penjualan,
			"is_total": 1
		}

		# Add division totals to grand total row
		for key, value in division_totals.items():
			grand_total_row[key] = value

		data.append(grand_total_row)

	return data
