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
	# Fixed columns for Sales Code and Sales Person Name
	columns = [
		{
			"label": _("Sales Code"),
			"fieldname": "sales_code",
			"fieldtype": "Data",
			"width": 90
		},
		{
			"label": _("Sales Person Name"),
			"fieldname": "sales_person_name",
			"fieldtype": "Data",
			"width": 180
		}
	]
	
	# Get all departments from the Dept table
	departments = frappe.get_all("Dept", fields=["dept_code", "dept_name"], order_by="dept_code")
	
	# Add a column for each department
	for dept in departments:
		columns.append({
			"label": _(dept.dept_name),
			"fieldname": f"dept_{dept.dept_code}",
			"fieldtype": "Currency",
			"width": 120
		})
	
	# Add a total column
	columns.append({
		"label": _("TOTAL"),
		"fieldname": "total_amount",
		"fieldtype": "Currency",
		"width": 120
	})
	
	return columns

def get_data(filters):
	# Get sales orders with items
	orders_with_items = get_sales_orders_with_items(filters)

	# Get sales invoices with items
	invoices_with_items = get_sales_invoices_with_items(filters)

	# Combine data from sales orders and sales invoices
	combined_data = orders_with_items + invoices_with_items

	# Pre-process to remove N/A entries if there are real sales persons for the same transaction
	processed_data = pre_process_data(combined_data)

	# Group data by sales person
	data = group_by_sales_person(processed_data)

	# Add grand total row
	data = add_grand_total(data)

	return data

def pre_process_data(combined_data):
	# Keep all entries, including N/A entries
	return combined_data

def get_sales_invoices_with_items(filters):
	# Build a simple query without the item_group filter first
	base_query = """
		SELECT name, posting_date
		FROM `tabSales Invoice`
		WHERE docstatus = 1
		AND DATE(posting_date) >= %(from_date)s
		AND DATE(posting_date) <= %(to_date)s
		AND company = %(company)s
	"""

	# Prepare base query parameters
	base_params = {
		"from_date": filters.get("from_date"),
		"to_date": filters.get("to_date"),
		"company": filters.get("company")
	}

	# Add branch filter if specified
	if filters.get("branch") and filters.get("branch").strip():
		base_query += " AND branch_id = %(branch)s"
		base_params["branch"] = filters.get("branch")

	# Get all sales invoices matching the base criteria
	base_sales_invoices = frappe.db.sql(base_query, base_params, as_dict=1)

	# If item_group filter is specified, filter the results further
	if filters.get("item_group"):
		filtered_sales_invoices = []
		for si in base_sales_invoices:
			# Check if this sales invoice has items in the specified item group
			items_in_group = frappe.db.sql("""
				SELECT 1 FROM `tabSales Invoice Item` sii
				JOIN `tabItem` item ON sii.item_code = item.name
				WHERE sii.parent = %s AND item.item_group = %s
				LIMIT 1
			""", (si.name, filters.get("item_group")), as_dict=1)

			if items_in_group:
				filtered_sales_invoices.append(si)

		sales_invoices = filtered_sales_invoices
	else:
		sales_invoices = base_sales_invoices

	result = []

	# For each sales invoice, get the sales team and items
	for si in sales_invoices:
		# Get items for this sales invoice
		items = frappe.get_all(
			"Sales Invoice Item",
			filters={"parent": si.name},
			fields=["item_code", "item_name", "item_group", "amount"]
		)

		# Skip if no items
		if not items:
			continue

		# Get department for each item
		for item in items:
			item_code = item.get("item_code")
			
			# Initialize department to empty
			item["dept"] = ""
			
			# Get department from item_dept field in Item table
			if item_code:
				try:
					dept = frappe.db.get_value("Item", item_code, "item_dept")
					if dept:
						item["dept"] = dept
				except:
					pass

		# Group items by department
		dept_totals = {}
		
		# Get all departments to ensure we have all keys
		all_depts = frappe.get_all("Dept", fields=["dept_code"])
		for dept in all_depts:
			dept_totals[dept.dept_code] = 0
		
		# Calculate department totals
		for item in items:
			dept = item.get("dept")
			amount = flt(item.get("amount"))
			
			# Only add to totals if department is explicitly set
			if dept and dept in dept_totals:
				dept_totals[dept] += amount

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
			# Make sure total allocation is 100%
			else:
				total_allocation = sum(flt(sp.get("allocated_percentage", 0)) for sp in sales_team)
				if total_allocation != 100.0:
					# Adjust allocations proportionally
					for sp in sales_team:
						sp["allocated_percentage"] = flt(sp.get("allocated_percentage", 0)) * 100.0 / total_allocation if total_allocation else 0
		except Exception as e:
			# Use 'N/A' as sales person if there's an error
			print(f"Error getting sales team for {si.name}: {str(e)}")
			sales_team = [{
				"sales_person": "N/A",
				"allocated_percentage": 100.0
			}]

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
				print(f"Sales person {sales_person_name} does not exist")
				sales_person_doc = frappe._dict({
					"name": "N/A",
					"sales_person_name": "Not Assigned",
					"sales_code": "N/A"
				})

			# Use amount based on allocated_percentage
			allocated_percent = flt(sp.get("allocated_percentage") if isinstance(sp, dict) else sp.allocated_percentage) / 100.0
			
			# Calculate department amounts based on allocation percentage
			dept_amounts = {}
			for dept_code, amount in dept_totals.items():
				dept_amounts[f"dept_{dept_code}"] = amount * allocated_percent

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
				"transaction_date": si.posting_date,
				"sales_invoice": si.name
			}

			# Add department amounts to the result
			for dept_field, amount in dept_amounts.items():
				result_entry[dept_field] = amount

			result.append(result_entry)

	return result

def get_sales_orders_with_items(filters):
	# Build a simple query without the item_group filter first
	base_query = """
		SELECT name, transaction_date
		FROM `tabSales Order`
		WHERE docstatus = 1
		AND DATE(transaction_date) >= %(from_date)s
		AND DATE(transaction_date) <= %(to_date)s
		AND company = %(company)s
	"""

	# Prepare base query parameters
	base_params = {
		"from_date": filters.get("from_date"),
		"to_date": filters.get("to_date"),
		"company": filters.get("company")
	}

	# Add branch filter if specified
	if filters.get("branch") and filters.get("branch").strip():
		base_query += " AND order_branch = %(branch)s"
		base_params["branch"] = filters.get("branch")

	# Get all sales orders matching the base criteria
	base_sales_orders = frappe.db.sql(base_query, base_params, as_dict=1)

	# If item_group filter is specified, filter the results further
	if filters.get("item_group"):
		filtered_sales_orders = []
		for so in base_sales_orders:
			# Check if this sales order has items in the specified item group
			items_in_group = frappe.db.sql("""
				SELECT 1 FROM `tabSales Order Item` soi
				JOIN `tabItem` item ON soi.item_code = item.name
				WHERE soi.parent = %s AND item.item_group = %s
				LIMIT 1
			""", (so.name, filters.get("item_group")), as_dict=1)

			if items_in_group:
				filtered_sales_orders.append(so)

		sales_orders = filtered_sales_orders
	else:
		sales_orders = base_sales_orders

	result = []

	# For each sales order, get the sales team and items
	for so in sales_orders:
		# Get items for this sales order with item_group
		items = frappe.get_all(
			"Sales Order Item",
			filters={"parent": so.name},
			fields=["item_code", "item_name", "item_group", "amount"]
		)

		# Skip if no items
		if not items:
			continue

		# Get department for each item
		for item in items:
			item_code = item.get("item_code")
			
			# Initialize department to empty
			item["dept"] = ""
			
			# Get department from item_dept field in Item table
			if item_code:
				try:
					dept = frappe.db.get_value("Item", item_code, "item_dept")
					if dept:
						item["dept"] = dept
				except:
					pass

		# Group items by department
		dept_totals = {}
		
		# Get all departments to ensure we have all keys
		all_depts = frappe.get_all("Dept", fields=["dept_code"])
		for dept in all_depts:
			dept_totals[dept.dept_code] = 0
		
		# Calculate department totals
		for item in items:
			dept = item.get("dept")
			amount = flt(item.get("amount"))
			
			# Only add to totals if department is explicitly set
			if dept and dept in dept_totals:
				dept_totals[dept] += amount

		# Get sales team for this sales order
		try:
			sales_team = frappe.get_all(
				"Sales Team",
				filters={"parent": so.name, "parenttype": "Sales Order"},
				fields=["sales_person", "allocated_percentage"]
			)

			# If no sales team, create a default entry with 100% allocation to "Not Assigned"
			if not sales_team:
				# Use 'N/A' as sales person if no sales team
				sales_team = [{
					"sales_person": "N/A",
					"allocated_percentage": 100.0
				}]
			# Make sure total allocation is 100%
			else:
				total_allocation = sum(flt(sp.get("allocated_percentage", 0)) for sp in sales_team)
				if total_allocation != 100.0:
					# Adjust allocations proportionally
					for sp in sales_team:
						sp["allocated_percentage"] = flt(sp.get("allocated_percentage", 0)) * 100.0 / total_allocation if total_allocation else 0
		except Exception as e:
			# Use 'N/A' as sales person if there's an error
			print(f"Error getting sales team for {so.name}: {str(e)}")
			sales_team = [{
				"sales_person": "N/A",
				"allocated_percentage": 100.0
			}]

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
				print(f"Sales person {sales_person_name} does not exist")
				sales_person_doc = frappe._dict({
					"name": "N/A",
					"sales_person_name": "Not Assigned",
					"sales_code": "N/A"
				})

			# Use amount based on allocated_percentage
			allocated_percent = flt(sp.get("allocated_percentage") if isinstance(sp, dict) else sp.allocated_percentage) / 100.0
			
			# Calculate department amounts based on allocation percentage
			dept_amounts = {}
			for dept_code, amount in dept_totals.items():
				dept_amounts[f"dept_{dept_code}"] = amount * allocated_percent

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
				"transaction_date": so.transaction_date,
				"sales_order": so.name
			}

			# Add department amounts to the result
			for dept_field, amount in dept_amounts.items():
				result_entry[dept_field] = amount

			result.append(result_entry)

	return result

def group_by_sales_person(orders_with_items):
	# Group by sales person and transaction
	sales_person_summary = {}
	# Track processed transactions globally to avoid double counting
	processed_transactions = set()

	# First pass: Process all transactions with assigned sales persons
	for row in orders_with_items:
		sales_person = row.get("sales_person")
		transaction_key = ""

		# Skip N/A entries in first pass
		if sales_person == "N/A":
			continue

		# Create a unique key for each transaction
		if row.get("sales_order"):
			transaction_key = f"SO-{row.get('sales_order')}"
		elif row.get("sales_invoice"):
			transaction_key = f"SI-{row.get('sales_invoice')}"
		else:
			continue  # Skip if no transaction reference

		# Add to processed transactions
		processed_transactions.add(transaction_key)

		# Initialize sales person entry if not exists
		if sales_person not in sales_person_summary:
			sales_person_summary[sales_person] = {
				"sales_code": row.get("sales_code"),
				"sales_person_name": row.get("sales_person_name"),
				"total_amount": 0,
				"transactions": set()  # Track processed transactions
			}
			
			# Initialize all department fields to 0
			all_depts = frappe.get_all("Dept", fields=["dept_code"])
			for dept in all_depts:
				sales_person_summary[sales_person][f"dept_{dept.dept_code}"] = 0

		# Check if this transaction has already been processed for this sales person
		if transaction_key in sales_person_summary[sales_person]["transactions"]:
			continue

		# Add transaction to processed list
		sales_person_summary[sales_person]["transactions"].add(transaction_key)

		# Add department values
		total_amount = 0
		for key, value in row.items():
			if key.startswith("dept_") and isinstance(value, (int, float)):
				sales_person_summary[sales_person][key] = flt(sales_person_summary[sales_person].get(key, 0)) + flt(value)
				total_amount += flt(value)
		
		# Update total amount
		sales_person_summary[sales_person]["total_amount"] += total_amount

	# Second pass: Process N/A entries only for transactions not already processed
	for row in orders_with_items:
		sales_person = row.get("sales_person")
		transaction_key = ""

		# Only process N/A entries in second pass
		if sales_person != "N/A":
			continue

		# Create a unique key for each transaction
		if row.get("sales_order"):
			transaction_key = f"SO-{row.get('sales_order')}"
		elif row.get("sales_invoice"):
			transaction_key = f"SI-{row.get('sales_invoice')}"
		else:
			continue  # Skip if no transaction reference

		# Skip if this transaction has already been processed
		if transaction_key in processed_transactions:
			continue

		# Initialize sales person entry if not exists
		if sales_person not in sales_person_summary:
			sales_person_summary[sales_person] = {
				"sales_code": row.get("sales_code"),
				"sales_person_name": row.get("sales_person_name"),
				"total_amount": 0,
				"transactions": set()  # Track processed transactions
			}
			
			# Initialize all department fields to 0
			all_depts = frappe.get_all("Dept", fields=["dept_code"])
			for dept in all_depts:
				sales_person_summary[sales_person][f"dept_{dept.dept_code}"] = 0

		# Check if this transaction has already been processed for this sales person
		if transaction_key in sales_person_summary[sales_person]["transactions"]:
			continue

		# Add transaction to processed list
		sales_person_summary[sales_person]["transactions"].add(transaction_key)

		# Add department values
		total_amount = 0
		for key, value in row.items():
			if key.startswith("dept_") and isinstance(value, (int, float)):
				sales_person_summary[sales_person][key] = flt(sales_person_summary[sales_person].get(key, 0)) + flt(value)
				total_amount += flt(value)
		
		# Update total amount
		sales_person_summary[sales_person]["total_amount"] += total_amount

	# Convert to list
	result = []
	for sales_person, summary in sales_person_summary.items():
		# Remove the transactions set before returning (not needed in output)
		if "transactions" in summary:
			del summary["transactions"]

		entry = {
			"sales_code": summary.get("sales_code", ""),
			"sales_person_name": summary["sales_person_name"],
			"total_amount": summary["total_amount"]
		}
		
		# Add department amounts
		for key, value in summary.items():
			if key.startswith("dept_"):
				entry[key] = value

		result.append(entry)

	# Sort by sales person name
	result = sorted(result, key=lambda x: x.get("sales_person_name") or "")

	return result

def add_grand_total(data):
	# Calculate grand totals
	if not data:
		return data
		
	# Initialize grand total row
	grand_total_row = {
		"sales_code": "",
		"sales_person_name": "<b>Grand Total</b>",
		"total_amount": 0,
		"is_total": 1
	}
	
	# Get all department fields from the first row
	dept_fields = [key for key in data[0].keys() if key.startswith("dept_")]
	
	# Initialize department totals in grand total row
	for dept_field in dept_fields:
		grand_total_row[dept_field] = 0
	
	# Calculate totals
	for row in data:
		# Add department totals
		for dept_field in dept_fields:
			grand_total_row[dept_field] += flt(row.get(dept_field, 0))
		
		# Add total amount
		grand_total_row["total_amount"] += flt(row.get("total_amount", 0))
	
	# Add grand total row
	data.append(grand_total_row)

	return data
