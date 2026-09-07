# Copyright (c) 2026, Reformiqo and contributors
# For license information, please see license.txt

"""Month-wise TCS movement within a fiscal year (FRD v3.0, Sheet 14, Report 2).

Shared by two reports that differ only in the side they read:

* TCS Receivable Monthly - Purchase Invoices, the TCS Receivable asset (mirrors TDS
  Payable Monthly on the purchase side).
* TCS Payable Monthly - Sales Invoices, the TCS Payable liability.

Only invoices that actually carried a TCS amount appear, with a subtotal per month and
a grand total, so the grand total equals the period movement in the ledger.
"""

import frappe
from frappe import _
from frappe.query_builder.functions import IfNull
from frappe.utils import add_months, flt, getdate

from palriwal.palriwal.tcs.report_utils import get_category_accounts, get_party_pan_map, get_side

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def execute(filters, party_type):
	filters = frappe._dict(filters or {})
	side = get_side(party_type)
	validate_filters(filters)
	return get_columns(side), get_data(filters, side)


def validate_filters(filters):
	if not filters.company:
		frappe.throw(_("Company is mandatory"))
	if not filters.fiscal_year:
		frappe.throw(_("Fiscal Year is mandatory"))

	fy = frappe.db.get_value(
		"Fiscal Year", filters.fiscal_year, ["year_start_date", "year_end_date"], as_dict=True
	)
	if not fy:
		frappe.throw(_("Fiscal Year {0} does not exist").format(filters.fiscal_year))

	filters.year_start_date = getdate(fy.year_start_date)
	filters.year_end_date = getdate(fy.year_end_date)

	# Months in fiscal-year order, e.g. Apr .. Mar for an Indian fiscal year
	months = []
	cursor = filters.year_start_date.replace(day=1)
	while cursor <= filters.year_end_date and len(months) < 12:
		months.append(MONTHS[cursor.month - 1])
		cursor = add_months(cursor, 1)
	filters.months = months

	start_idx = months.index(filters.from_month) if filters.from_month in months else 0
	end_idx = months.index(filters.to_month) if filters.to_month in months else len(months) - 1
	if start_idx > end_idx:
		frappe.throw(_("From Month cannot be after To Month within the fiscal year"))
	filters.selected_months = months[start_idx : end_idx + 1]


def get_columns(side):
	party_type = side.party_type
	return [
		{"label": _("Month"), "fieldname": "month", "fieldtype": "Data", "width": 100},
		{"label": _("Section"), "fieldname": "section", "fieldtype": "Data", "width": 100},
		{
			"label": _(side.doctype),
			"fieldname": "invoice",
			"fieldtype": "Link",
			"options": side.doctype,
			"width": 150,
		},
		{"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{
			"label": _(party_type),
			"fieldname": "party",
			"fieldtype": "Link",
			"options": party_type,
			"width": 180,
		},
		{
			"label": _("{0} PAN").format(_(party_type)),
			"fieldname": "party_pan",
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"label": _("Base Amount"),
			"fieldname": "base_amount",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 130,
		},
		{"label": _("TCS Rate (%)"), "fieldname": "tcs_rate", "fieldtype": "Percent", "width": 90},
		{
			"label": _("TCS Amount"),
			"fieldname": "tcs_amount",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 130,
		},
		{
			"label": _(side.account_label),
			"fieldname": "tcs_account",
			"fieldtype": "Link",
			"options": "Account",
			"width": 200,
		},
		{
			"label": _("Currency"),
			"fieldname": "currency",
			"fieldtype": "Link",
			"options": "Currency",
			"hidden": 1,
		},
	]


def get_invoices(filters, side):
	inv = frappe.qb.DocType(side.doctype)
	party = inv[side.party_field]
	query = (
		frappe.qb.from_(inv)
		.select(
			inv.name,
			party.as_("party"),
			inv.posting_date,
			inv.custom_tcs_category,
			inv.custom_tcs_section,
			inv.custom_tcs_rate,
			inv.custom_tcs_base_amount,
			inv.custom_tcs_amount,
		)
		.where(inv.docstatus == 1)
		.where(inv.company == filters.company)
		.where(inv.custom_apply_tcs == 1)
		.where(IfNull(inv.custom_tcs_category, "") != "")
		.where(IfNull(inv.custom_tcs_amount, 0) != 0)
		.where(inv.posting_date >= filters.year_start_date)
		.where(inv.posting_date <= filters.year_end_date)
		.orderby(inv.posting_date)
		.orderby(inv.name)
	)
	if filters.party:
		query = query.where(party == filters.party)
	if filters.tcs_category:
		query = query.where(inv.custom_tcs_category == filters.tcs_category)

	return query.run(as_dict=True)


def get_data(filters, side):
	invoices = get_invoices(filters, side)
	if not invoices:
		return []

	company_currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	accounts = get_category_accounts(
		{inv.custom_tcs_category for inv in invoices}, filters.company, side.account_field
	)
	pan_map = get_party_pan_map(side.party_type, {inv.party for inv in invoices})

	by_month = {}
	for inv in invoices:
		month = MONTHS[getdate(inv.posting_date).month - 1]
		if month not in filters.selected_months:
			continue
		by_month.setdefault(month, []).append(inv)

	data = []
	grand_base = grand_amount = 0.0

	for month in filters.selected_months:
		rows = by_month.get(month)
		if not rows:
			continue

		month_base = month_amount = 0.0
		for inv in rows:
			data.append(
				{
					"month": month,
					"section": inv.custom_tcs_section,
					"invoice": inv.name,
					"posting_date": inv.posting_date,
					"party": inv.party,
					"party_pan": pan_map.get(inv.party),
					"base_amount": flt(inv.custom_tcs_base_amount),
					"tcs_rate": flt(inv.custom_tcs_rate),
					"tcs_amount": flt(inv.custom_tcs_amount),
					"tcs_account": accounts.get(inv.custom_tcs_category),
					"currency": company_currency,
				}
			)
			month_base += flt(inv.custom_tcs_base_amount)
			month_amount += flt(inv.custom_tcs_amount)

		data.append(
			{
				"month": _("{0} Total").format(month),
				"base_amount": month_base,
				"tcs_amount": month_amount,
				"currency": company_currency,
				"is_subtotal_row": 1,
			}
		)
		grand_base += month_base
		grand_amount += month_amount

	if data:
		data.append(
			{
				"month": _("Grand Total"),
				"base_amount": grand_base,
				"tcs_amount": grand_amount,
				"currency": company_currency,
				"is_total_row": 1,
			}
		)

	return data
