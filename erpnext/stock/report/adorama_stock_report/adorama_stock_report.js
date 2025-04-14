// Copyright (c) 2023, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.query_reports["Adorama Stock Report"] = {
	"filters": [
		{
			"fieldname": "company",
			"label": __("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"default": frappe.defaults.get_user_default("Company"),
			"reqd": 1
		},
		{
			"fieldname": "date",
			"label": __("Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today(),
			"reqd": 1
		},
		{
			"fieldname": "item_code",
			"label": __("Item"),
			"fieldtype": "Link",
			"options": "Item"
		},
		{
			"fieldname": "item_group",
			"label": __("Item Group"),
			"fieldtype": "Link",
			"options": "Item Group"
		}
	],
	"formatter": function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		// No special formatting for warehouse columns

		if (column.fieldname === "transfer" && value === "Transfer") {
			value = `<button class="btn btn-xs btn-default" onclick="frappe.query_reports['Adorama Stock Report'].create_stock_entry('${data.item_code}')">Transfer</button>`;
		}

		return value;
	},

	"create_stock_entry": function (item_code) {
		frappe.model.with_doctype('Stock Entry', function () {
			var doc = frappe.model.get_new_doc('Stock Entry');
			doc.stock_entry_type = 'Material Transfer';

			var row = frappe.model.add_child(doc, 'items');
			row.item_code = item_code;
			row.qty = 1;

			frappe.set_route('Form', doc.doctype, doc.name);
		});
	}
};
