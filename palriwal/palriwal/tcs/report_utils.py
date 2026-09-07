# Copyright (c) 2026, Reformiqo and contributors
# For license information, please see license.txt

"""Helpers shared by the two TCS reports (FRD v3.0, Sheet 14)."""

import frappe
from frappe.utils import flt


def get_category_settings(categories):
	if not categories:
		return {}
	rows = frappe.get_all(
		"TCS Category",
		filters={"name": ("in", list(categories))},
		fields=["name", "calculation_base", "statutory_section", "nature_of_collection"],
	)
	return {row.name: row for row in rows}


def get_category_accounts(categories, company):
	"""Category -> TCS Receivable account mapped for the company."""
	if not categories:
		return {}
	rows = frappe.get_all(
		"TCS Account",
		filters={"parent": ("in", list(categories)), "parenttype": "TCS Category", "company": company},
		fields=["parent", "account"],
	)
	return {row.parent: row.account for row in rows}


def get_supplier_pan_map(suppliers):
	if not suppliers:
		return {}
	meta = frappe.get_meta("Supplier")
	fieldname = "pan" if meta.has_field("pan") else "tax_id"
	rows = frappe.get_all(
		"Supplier", filters={"name": ("in", list(suppliers))}, fields=["name", f"{fieldname} as pan"]
	)
	return {row.name: row.pan for row in rows}


def invoice_base(inv, category_settings):
	"""The same base the engine used for the cumulative party total (engine step 6)."""
	if category_settings and category_settings.calculation_base == "Net Total":
		return flt(inv.base_net_total)
	return flt(inv.base_grand_total) - flt(inv.custom_tcs_amount)
