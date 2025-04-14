# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class StockSending(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from erpnext.stock.doctype.stock_sending_detail.stock_sending_detail import StockSendingDetail
		from frappe.types import DF

		amended_from: DF.Link | None
		d_warehouse: DF.Link
		naming_series: DF.Literal["SND-.YYYY.-"]
		tbl_detail: DF.Table[StockSendingDetail]
	# end: auto-generated types
	pass
