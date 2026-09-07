# Copyright (c) 2026, Reformiqo and contributors
# For license information, please see license.txt

"""TCS Computation Summary - mirrors TDS Computation Summary (FRD v3.0, Sheet 14, Report 1).

Supplier-wise and section-wise view of every submitted Purchase Invoice that carried
Apply TCS, with the base, rate, amount, threshold status and a running cumulative base
for the financial year. Tie-out rule: the TCS Amount total for a period equals the total
debit to the TCS Receivable account(s) in the General Ledger for the same period.
"""

import frappe
from erpnext.accounts.utils import get_fiscal_year
from frappe import _
from frappe.query_builder.functions import IfNull
from frappe.utils import flt, getdate

from palriwal.palriwal.tcs.report_utils import (
	get_category_accounts,
	get_category_settings,
	get_supplier_pan_map,
	invoice_base,
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)
	return get_columns(), get_data(filters)


def validate_filters(filters):
	if not filters.company:
		frappe.throw(_("Company is mandatory"))
	if not filters.from_date or not filters.to_date:
		frappe.throw(_("From Date and To Date are mandatory"))
	if getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date"))

	if filters.fiscal_year:
		fy = frappe.db.get_value(
			"Fiscal Year", filters.fiscal_year, ["year_start_date", "year_end_date"], as_dict=True
		)
		if fy and not (fy.year_start_date <= getdate(filters.from_date) <= fy.year_end_date):
			frappe.throw(_("From Date does not fall in Fiscal Year {0}").format(filters.fiscal_year))

	from_fy = get_fiscal_year(filters.from_date, company=filters.company)
	to_fy = get_fiscal_year(filters.to_date, company=filters.company)
	if from_fy[0] != to_fy[0]:
		frappe.throw(_("From Date and To Date lie in different Fiscal Years"))

	filters.fy_start = getdate(from_fy[1])
	filters.fy_end = getdate(from_fy[2])


def get_columns():
	return [
		{
			"label": _("Supplier"),
			"fieldname": "supplier",
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 180,
		},
		{"label": _("Supplier PAN"), "fieldname": "supplier_pan", "fieldtype": "Data", "width": 110},
		{
			"label": _("TCS Category"),
			"fieldname": "tcs_category",
			"fieldtype": "Link",
			"options": "TCS Category",
			"width": 180,
		},
		{"label": _("Section"), "fieldname": "section", "fieldtype": "Data", "width": 100},
		{
			"label": _("Purchase Invoice"),
			"fieldname": "purchase_invoice",
			"fieldtype": "Link",
			"options": "Purchase Invoice",
			"width": 150,
		},
		{"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{
			"label": _("Base Total"),
			"fieldname": "base_total",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 130,
		},
		{
			"label": _("Invoice Grand Total"),
			"fieldname": "grand_total",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 140,
		},
		{"label": _("TCS Rate (%)"), "fieldname": "tcs_rate", "fieldtype": "Percent", "width": 90},
		{
			"label": _("TCS Amount"),
			"fieldname": "tcs_amount",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 130,
		},
		{"label": _("Threshold Status"), "fieldname": "threshold_status", "fieldtype": "Data", "width": 180},
		{
			"label": _("Cumulative Base (FY)"),
			"fieldname": "cumulative_base",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 150,
		},
		{
			"label": _("TCS Account"),
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


def get_invoices(filters):
	"""Every submitted TCS invoice from the start of the financial year up to To Date.

	The whole year is read so the cumulative base is correct even when From Date is
	later than the year start; rows before From Date are dropped after accumulating.
	"""
	pi = frappe.qb.DocType("Purchase Invoice")
	query = (
		frappe.qb.from_(pi)
		.select(
			pi.name,
			pi.supplier,
			pi.posting_date,
			pi.is_return,
			pi.base_net_total,
			pi.base_grand_total,
			pi.custom_tcs_category,
			pi.custom_tcs_section,
			pi.custom_tcs_rate,
			pi.custom_tcs_base_amount,
			pi.custom_tcs_amount,
			pi.custom_tcs_threshold_status,
		)
		.where(pi.docstatus == 1)
		.where(pi.company == filters.company)
		.where(pi.custom_apply_tcs == 1)
		.where(IfNull(pi.custom_tcs_category, "") != "")
		.where(IfNull(pi.is_opening, "No") != "Yes")
		.where(pi.posting_date >= filters.fy_start)
		.where(pi.posting_date <= getdate(filters.to_date))
		.orderby(pi.supplier)
		.orderby(pi.custom_tcs_category)
		.orderby(pi.posting_date)
		.orderby(pi.name)
	)
	if filters.supplier:
		query = query.where(pi.supplier == filters.supplier)
	if filters.tcs_category:
		query = query.where(pi.custom_tcs_category == filters.tcs_category)

	return query.run(as_dict=True)


def get_data(filters):
	invoices = get_invoices(filters)
	if not invoices:
		return []

	company_currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	categories = {inv.custom_tcs_category for inv in invoices}
	settings = get_category_settings(categories)
	accounts = get_category_accounts(categories, filters.company)
	pan_map = get_supplier_pan_map({inv.supplier for inv in invoices})

	from_date = getdate(filters.from_date)
	running = {}
	data = []
	total_base = total_amount = 0.0

	for inv in invoices:
		key = (inv.supplier, inv.custom_tcs_category)
		running[key] = running.get(key, 0.0) + invoice_base(inv, settings.get(inv.custom_tcs_category))

		if getdate(inv.posting_date) < from_date:
			continue
		if filters.threshold_status and inv.custom_tcs_threshold_status != filters.threshold_status:
			continue

		data.append(
			{
				"supplier": inv.supplier,
				"supplier_pan": pan_map.get(inv.supplier),
				"tcs_category": inv.custom_tcs_category,
				"section": inv.custom_tcs_section,
				"purchase_invoice": inv.name,
				"posting_date": inv.posting_date,
				"base_total": flt(inv.custom_tcs_base_amount),
				"grand_total": flt(inv.base_grand_total),
				"tcs_rate": flt(inv.custom_tcs_rate),
				"tcs_amount": flt(inv.custom_tcs_amount),
				"threshold_status": inv.custom_tcs_threshold_status,
				"cumulative_base": running[key],
				"tcs_account": accounts.get(inv.custom_tcs_category),
				"currency": company_currency,
			}
		)
		total_base += flt(inv.custom_tcs_base_amount)
		total_amount += flt(inv.custom_tcs_amount)

	if data:
		data.append(
			{
				"supplier": _("Total"),
				"base_total": total_base,
				"tcs_amount": total_amount,
				"currency": company_currency,
				"is_total_row": 1,
			}
		)

	return data
