# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt


import copy

import frappe
from frappe.model.document import Document


class Brand(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF
		from frappe.core.doctype.has_role.has_role import HasRole

		brand: DF.Data
		brand_sku: DF.Data
		brand_defaults: DF.Table[HasRole]
	# end: auto-generated types

	pass


def get_brand_defaults(item, company):
	item = frappe.get_cached_doc("Item", item)
	if item.brand:
		brand = frappe.get_cached_doc("Brand", item.brand)

		# Check if brand_defaults attribute exists
		if hasattr(brand, 'brand_defaults') and brand.brand_defaults:
			for d in brand.brand_defaults:
				if d.company == company:
					row = copy.deepcopy(d.as_dict())
					row.pop("name")
					return row

	return frappe._dict()
