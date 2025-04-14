# Copyright (c) 2023, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt

def execute(filters=None):
	if not filters:
		filters = {}

	# Get all warehouses
	warehouses = get_warehouses(filters)

	# Define columns
	columns = get_columns(warehouses)

	# Get items based on filters
	items = get_items(filters)

	# Get stock balances for each item in each warehouse
	item_map = get_item_warehouse_map(filters, warehouses, items)

	# Prepare data for report
	data = prepare_data(filters, items, item_map, warehouses)

	return columns, data

def get_columns(warehouses):
	columns = [
		{
			"label": _("Item"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 140
		},
		{
			"label": _("Item Group"),
			"fieldname": "item_group",
			"fieldtype": "Link",
			"options": "Item Group",
			"width": 140
		},
		{
			"label": _("Item Name"),
			"fieldname": "item_name",
			"fieldtype": "Data",
			"width": 200
		}
	]

	# Add warehouse columns
	for warehouse in warehouses:
		columns.append({
			"label": _(warehouse),
			"fieldname": warehouse,
			"fieldtype": "Float",
			"width": 120
		})

	# Add transfer button column
	columns.append({
		"label": _("Transfer"),
		"fieldname": "transfer",
		"fieldtype": "Button",
		"width": 100
	})

	return columns

def get_warehouses(filters):
	# List of specific warehouses to display
	specific_warehouses = [
		"MENTENG - ADO",
		"KEMANG - ADO",
		"CIKAJANG - ADO",
		"SENAYAN - ADO",
		"MEC - ADO",
		"PUSAT MENTENG - ADO",
		"PUSAT KEMANG - ADO"
	]

	# Filter warehouses by company and name
	warehouse_filters = {
		"company": filters.get("company"),
		"name": ["in", specific_warehouses]
	}

	warehouse_list = frappe.get_all(
		"Warehouse",
		filters=warehouse_filters,
		fields=["name"],
		order_by="name"
	)

	return [warehouse.name for warehouse in warehouse_list]

def get_items(filters):
	item_filters = {}

	if filters.get("item_code"):
		item_filters["item_code"] = filters.get("item_code")

	if filters.get("item_group"):
		item_filters["item_group"] = filters.get("item_group")

	items = frappe.get_all(
		"Item",
		filters=item_filters,
		fields=["name as item_code", "item_name", "item_group"],
		order_by="item_code"
	)

	return items

def get_item_warehouse_map(filters, warehouses, items):
	item_map = {}
	item_codes = [item.item_code for item in items]

	if not item_codes:
		return item_map

	date = filters.get("date")

	stock_ledger_entries = frappe.db.sql("""
		SELECT
			item_code, warehouse, SUM(actual_qty) as qty
		FROM
			`tabStock Ledger Entry`
		WHERE
			company = %s
			AND item_code IN %s
			AND posting_date <= %s
		GROUP BY
			item_code, warehouse
	""", (filters.get("company"), item_codes, date), as_dict=1)

	for entry in stock_ledger_entries:
		item_code = entry.item_code
		warehouse = entry.warehouse
		qty = flt(entry.qty)

		if item_code not in item_map:
			item_map[item_code] = {}

		item_map[item_code][warehouse] = qty

	return item_map

def prepare_data(filters, items, item_map, warehouses):
	data = []

	for item in items:
		row = {
			"item_code": item.item_code,
			"item_group": item.item_group,
			"item_name": item.item_name,
			"transfer": "Transfer"
		}

		# Add warehouse quantities
		for warehouse in warehouses:
			row[warehouse] = flt(item_map.get(item.item_code, {}).get(warehouse, 0))

		data.append(row)

	return data
