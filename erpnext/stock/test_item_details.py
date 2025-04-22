import frappe
import json
import traceback
from erpnext.stock.get_item_details import get_item_details

def execute():
    try:
        # Prepare the arguments
        args = {
            "item_code": "FAFBFMB001",
            "price_list": "Penjualan MEC",
            "company": "Adorama",
            "qty": 27,
            "transaction_type": "selling",
            "doctype": "Sales Order",
            "currency": "IDR"
        }

        # Call the function
        print("Calling get_item_details with args:")
        print(json.dumps(args, indent=2))
        print("\n")

        result = get_item_details(args)

        # Print the result
        print("Result:")
        print(json.dumps(result, indent=2, default=str))

        # Print specific fields of interest
        print("\nImportant fields:")
        important_fields = ['item_code', 'item_name', 'price_list_rate', 'rate', 'amount', 'stock_qty']
        for field in important_fields:
            if field in result:
                print(f"{field}: {result[field]}")
            else:
                print(f"{field}: Not found")

    except Exception as e:
        print(f"Error: {e}")
        print("Traceback:")
        traceback.print_exc()
        frappe.log_error(f"Error testing get_item_details: {str(e)}", "Test Error")
