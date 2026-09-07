# Copyright (c) 2026, Reformiqo and contributors
# For license information, please see license.txt

"""Helpers shared by the TCS reports (FRD v3.0, Sheet 14)."""

import frappe
from frappe.utils import flt

# Which invoice, party and account column each side of the engine uses.
SIDES = {
	"Supplier": frappe._dict(
		party_type="Supplier",
		party_field="supplier",
		doctype="Purchase Invoice",
		account_field="account",
		account_label="TCS Receivable Account",
	),
	"Customer": frappe._dict(
		party_type="Customer",
		party_field="customer",
		doctype="Sales Invoice",
		account_field="payable_account",
		account_label="TCS Payable Account",
	),
}


def get_side(party_type):
	return SIDES.get(party_type or "Supplier", SIDES["Supplier"])


def get_category_settings(categories):
	if not categories:
		return {}
	rows = frappe.get_all(
		"TCS Category",
		filters={"name": ("in", list(categories))},
		fields=["name", "calculation_base", "statutory_section", "nature_of_collection"],
	)
	return {row.name: row for row in rows}


def get_category_accounts(categories, company, account_field="account"):
	"""Category -> account mapped for the company on the requested side."""
	if not categories:
		return {}
	rows = frappe.get_all(
		"TCS Account",
		filters={"parent": ("in", list(categories)), "parenttype": "TCS Category", "company": company},
		fields=["parent", account_field],
	)
	return {row.parent: row.get(account_field) for row in rows}


def get_party_pan_map(party_type, parties):
	if not parties:
		return {}
	meta = frappe.get_meta(party_type)
	fieldname = "pan" if meta.has_field("pan") else "tax_id"
	rows = frappe.get_all(
		party_type, filters={"name": ("in", list(parties))}, fields=["name", f"{fieldname} as pan"]
	)
	return {row.name: row.pan for row in rows}


def get_supplier_pan_map(suppliers):
	return get_party_pan_map("Supplier", suppliers)


def invoice_base(inv, category_settings):
	"""The same base the engine used for the cumulative party total (engine step 6)."""
	if category_settings and category_settings.calculation_base == "Net Total":
		return flt(inv.base_net_total)
	return flt(inv.base_grand_total) - flt(inv.custom_tcs_amount)
