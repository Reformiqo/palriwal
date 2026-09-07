# Copyright (c) 2026, Reformiqo and contributors
# For license information, please see license.txt

"""Custom fields for the TCS engine (FRD v3.0, Sheet 9).

One link on Supplier and on Customer, a section with seven fields on Purchase Invoice
and on Sales Invoice, and one hidden flag on Purchase Taxes and Charges and on Sales
Taxes and Charges. Created idempotently from ``after_install`` and ``after_migrate``
(hooks.py) so a plain ``bench migrate`` keeps a site in sync.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

MODULE = "Palriwal"

# The four defined Threshold Status values plus the FR-030 foreign-currency reason.
THRESHOLD_STATUS_DESCRIPTION = (
	"One of: Below Single and Cumulative, Single Threshold Crossed, "
	"Cumulative Threshold Crossed, No Threshold Configured. Display only."
)


def get_custom_fields():
	return {
		"Supplier": [
			{
				"fieldname": "custom_tcs_category",
				"label": "TCS Category",
				"fieldtype": "Link",
				"options": "TCS Category",
				"insert_after": "tax_withholding_category",
				"description": "Applied to this supplier's Purchase Invoices, exactly like Tax Withholding Category for TDS.",
				"module": MODULE,
			},
		],
		"Customer": [
			{
				"fieldname": "custom_tcs_category",
				"label": "TCS Category",
				"fieldtype": "Link",
				"options": "TCS Category",
				"insert_after": "tax_withholding_category",
				"description": "Applied to this customer's Sales Invoices, exactly like Tax Withholding Category for TCS under the native engine.",
				"module": MODULE,
			},
		],
		"Purchase Invoice": get_invoice_fields("Purchase Invoice"),
		"Sales Invoice": get_invoice_fields("Sales Invoice"),
		"Purchase Taxes and Charges": [get_tcs_row_flag()],
		"Sales Taxes and Charges": [get_tcs_row_flag()],
	}


def get_tcs_row_flag():
	return {
		"fieldname": "custom_is_tcs_row",
		"label": "Is TCS Row",
		"fieldtype": "Check",
		"insert_after": "is_tax_withholding_account",
		"hidden": 1,
		"read_only": 1,
		"no_copy": 1,
		"print_hide": 1,
		"description": "Marks the row owned by the TCS engine. Only this row is ever created, updated or deleted by the engine.",
		"module": MODULE,
	}


def get_invoice_fields(doctype):
	party = "supplier" if doctype == "Purchase Invoice" else "customer"
	return [
		{
			"fieldname": "custom_tcs_sb",
			"label": "TCS",
			"fieldtype": "Section Break",
			"collapsible": 1,
			"collapsible_depends_on": "eval:doc.custom_apply_tcs",
			# immediately after the standard Tax Withholding section (Sheet 9)
			"insert_after": "tax_withholding_entries",
			"module": MODULE,
		},
		{
			"fieldname": "custom_apply_tcs",
			"label": "Apply TCS",
			"fieldtype": "Check",
			"insert_after": "custom_tcs_sb",
			"print_hide": 1,
			"description": f"Defaults to ticked when the {party} has a TCS Category.",
			"module": MODULE,
		},
		{
			"fieldname": "custom_tcs_category",
			"label": "TCS Category",
			"fieldtype": "Link",
			"options": "TCS Category",
			"insert_after": "custom_apply_tcs",
			"depends_on": "eval:doc.custom_apply_tcs",
			"print_hide": 1,
			"module": MODULE,
		},
		{
			"fieldname": "custom_tcs_section",
			"label": "TCS Section",
			"fieldtype": "Data",
			"insert_after": "custom_tcs_category",
			"read_only": 1,
			"no_copy": 1,
			"print_hide": 1,
			"depends_on": "eval:doc.custom_apply_tcs",
			"module": MODULE,
		},
		{
			"fieldname": "custom_tcs_cb",
			"fieldtype": "Column Break",
			"insert_after": "custom_tcs_section",
			"module": MODULE,
		},
		{
			"fieldname": "custom_tcs_rate",
			"label": "TCS Rate (%)",
			"fieldtype": "Percent",
			"insert_after": "custom_tcs_cb",
			"read_only": 1,
			"no_copy": 1,
			"print_hide": 1,
			"depends_on": "eval:doc.custom_apply_tcs",
			"module": MODULE,
		},
		{
			"fieldname": "custom_tcs_base_amount",
			"label": "TCS Base Amount",
			"fieldtype": "Currency",
			"options": "Company:company:default_currency",
			"insert_after": "custom_tcs_rate",
			"read_only": 1,
			"no_copy": 1,
			"print_hide": 1,
			"depends_on": "eval:doc.custom_apply_tcs",
			"description": "The amount the rate was applied to, after threshold logic.",
			"module": MODULE,
		},
		{
			"fieldname": "custom_tcs_amount",
			"label": "TCS Amount",
			"fieldtype": "Currency",
			"options": "Company:company:default_currency",
			"insert_after": "custom_tcs_base_amount",
			"read_only": 1,
			"no_copy": 1,
			"print_hide": 1,
			"depends_on": "eval:doc.custom_apply_tcs",
			"description": "System calculated. No manual override.",
			"module": MODULE,
		},
		{
			"fieldname": "custom_tcs_threshold_status",
			"label": "Threshold Status",
			"fieldtype": "Data",
			"insert_after": "custom_tcs_amount",
			"read_only": 1,
			"no_copy": 1,
			"print_hide": 1,
			"depends_on": "eval:doc.custom_apply_tcs",
			"description": THRESHOLD_STATUS_DESCRIPTION,
			"module": MODULE,
		},
	]


def setup_custom_fields():
	"""Create (or update) the TCS custom fields. Safe to run repeatedly."""
	create_custom_fields(get_custom_fields(), ignore_validate=frappe.flags.in_patch, update=True)
	frappe.clear_cache()
