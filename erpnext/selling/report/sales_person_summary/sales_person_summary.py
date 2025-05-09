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
			"width": 90
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

	# Debug: Print raw data
	# print("\nOrders with items:")
	# for order in orders_with_items:
	# 	print(f"Order: {order.get('sales_order')}, Sales Person: {order.get('sales_person')}, B: {order.get('penjualan_barang')}, F: {order.get('penjualan_cuci_cetak')}")

	# print("\nInvoices with items:")
	# for invoice in invoices_with_items:
	# 	print(f"Invoice: {invoice.get('sales_invoice')}, Sales Person: {invoice.get('sales_person')}, B: {invoice.get('penjualan_barang')}, F: {invoice.get('penjualan_cuci_cetak')}")

	# Combine data from sales orders and sales invoices
	combined_data = orders_with_items + invoices_with_items

	# Pre-process to remove N/A entries if there are real sales persons for the same transaction
	processed_data = pre_process_data(combined_data)

	# Debug: Print combined data
	# print("\nCombined data after pre-processing:")
	# for item in processed_data:
	# 	print(f"Item: {item.get('sales_order') or item.get('sales_invoice')}, Sales Person: {item.get('sales_person')}, B: {item.get('penjualan_barang')}, F: {item.get('penjualan_cuci_cetak')}")

	# Group data by sales person
	data = group_by_sales_person(processed_data)

	# Debug: Print grouped data
	# print("\nGrouped data:")
	# for item in data:
	# 	print(f"Sales Person: {item.get('sales_person_name')}, B: {item.get('penjualan_barang')}, F: {item.get('penjualan_cuci_cetak')}, Total: {item.get('total_penjualan')}")

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

	# Debug: Print all sales invoices
	# print("\nAll Sales Invoices:")
	# for si in sales_invoices:
	# 	print(f"SI: {si.name}, Date: {si.posting_date}")

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

		# Debug: Print items for this sales invoice
		# print(f"\nItems for {si.name}:")
		# for item in items:
		# 	print(f"Item: {item.item_code}, Amount: {item.amount}")

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

		# Debug: Print division totals
		# print(f"Division totals for {si.name}: B={division_totals['B']}, F={division_totals['F']}")

		# Get sales team for this sales invoice
		try:
			sales_team = frappe.get_all(
				"Sales Team",
				filters={"parent": si.name, "parenttype": "Sales Invoice"},
				fields=["sales_person", "allocated_percentage"]
			)

			# Debug: Print sales team
			# print(f"Sales team for {si.name}: {sales_team}")

			# If no sales team, create a default entry with 100% allocation to "N/A"
			if not sales_team:
				sales_team = [{
					"sales_person": "N/A",
					"allocated_percentage": 100.0
				}]
				# print(f"No sales team for {si.name}, using N/A")
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
			penjualan_barang = flt(division_totals.get("B", 0)) * allocated_percent
			penjualan_cuci_cetak = flt(division_totals.get("F", 0)) * allocated_percent

			# Debug: Print calculated values
			# print(f"Calculated values for {sales_person_doc.sales_person_name}: B={penjualan_barang}, F={penjualan_cuci_cetak}")

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

	# Process results without logging

	# Continue even if no sales orders found

	result = []

	# Debug: Print all sales orders
	# print("\nAll Sales Orders:")
	# for so in sales_orders:
	# 	print(f"SO: {so.name}, Date: {so.transaction_date}")

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

		# Debug: Print items for this sales order
		# print(f"\nItems for {so.name}:")
		# for item in items:
		# 	print(f"Item: {item.item_code}, Amount: {item.amount}")

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

		# Debug: Print division totals
		# print(f"Division totals for {so.name}: B={division_totals['B']}, F={division_totals['F']}")

		# Get sales team for this sales order
		try:
			sales_team = frappe.get_all(
				"Sales Team",
				filters={"parent": so.name, "parenttype": "Sales Order"},
				fields=["sales_person", "allocated_percentage"]
			)

			# Debug: Print sales team
			# print(f"Sales team for {so.name}: {sales_team}")

			# If no sales team, create a default entry with 100% allocation to "Not Assigned"
			if not sales_team:
				# Use 'N/A' as sales person if no sales team
				sales_team = [{
					"sales_person": "N/A",
					"allocated_percentage": 100.0
				}]
				# print(f"No sales team for {so.name}, using N/A")
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
			penjualan_barang = flt(division_totals.get("B", 0)) * allocated_percent
			penjualan_cuci_cetak = flt(division_totals.get("F", 0)) * allocated_percent

			# Debug: Print calculated values
			# print(f"Calculated values for {sales_person_doc.sales_person_name}: B={penjualan_barang}, F={penjualan_cuci_cetak}")

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
				"transaction_date": so.transaction_date,
				"sales_order": so.name
			}

			# Add other divisions to the result
			for div_code, amount in other_divisions.items():
				result_entry[f"division_{div_code}"] = amount

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
				"penjualan_barang": 0,
				"penjualan_cuci_cetak": 0,
				"total_penjualan": 0,
				"transactions": set()  # Track processed transactions
			}

		# Check if this transaction has already been processed for this sales person
		if transaction_key in sales_person_summary[sales_person]["transactions"]:
			continue

		# Add transaction to processed list
		sales_person_summary[sales_person]["transactions"].add(transaction_key)

		# Add values
		sales_person_summary[sales_person]["penjualan_barang"] += flt(row.get("penjualan_barang"))
		sales_person_summary[sales_person]["penjualan_cuci_cetak"] += flt(row.get("penjualan_cuci_cetak"))

		# Calculate total penjualan
		sales_person_summary[sales_person]["total_penjualan"] = flt(sales_person_summary[sales_person]["penjualan_barang"]) + flt(sales_person_summary[sales_person]["penjualan_cuci_cetak"])

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
				"penjualan_barang": 0,
				"penjualan_cuci_cetak": 0,
				"total_penjualan": 0,
				"transactions": set()  # Track processed transactions
			}

		# Check if this transaction has already been processed for this sales person
		if transaction_key in sales_person_summary[sales_person]["transactions"]:
			continue

		# Add transaction to processed list
		sales_person_summary[sales_person]["transactions"].add(transaction_key)

		# Add values
		sales_person_summary[sales_person]["penjualan_barang"] += flt(row.get("penjualan_barang"))
		sales_person_summary[sales_person]["penjualan_cuci_cetak"] += flt(row.get("penjualan_cuci_cetak"))

		# Calculate total penjualan
		sales_person_summary[sales_person]["total_penjualan"] = flt(sales_person_summary[sales_person]["penjualan_barang"]) + flt(sales_person_summary[sales_person]["penjualan_cuci_cetak"])

	# Convert to list
	result = []
	for sales_person, summary in sales_person_summary.items():
		# Include entries with zero values
		# Commented out to include entries with zero values
		# if summary["total_penjualan"] == 0:
		# 	continue

		# Remove the transactions set before returning (not needed in output)
		if "transactions" in summary:
			del summary["transactions"]

		entry = {
			"sales_code": summary.get("sales_code", ""),
			"sales_person_name": summary["sales_person_name"],
			"penjualan_barang": summary["penjualan_barang"],
			"penjualan_cuci_cetak": summary["penjualan_cuci_cetak"],
			"total_penjualan": summary["total_penjualan"]
		}

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
