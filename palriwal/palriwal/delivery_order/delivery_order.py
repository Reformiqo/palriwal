# Copyright (c) 2026, Reformiqo and contributors
# For license information, please see license.txt

"""Delivery Order side of the flow: its own validate hook, the "Create Delivery Note" button
and the "Create Payment" button (ported from the "Making Payment Entry from Delivery Out for
linked PO - N" Server Script, same accounts and duplicate rule).
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, get_link_to_form, nowdate

from palriwal.palriwal.delivery_order.purchase_order import validate_against_purchase_order
from palriwal.palriwal.delivery_order.qty_math import rounded
from palriwal.palriwal.delivery_order.quantities import (
	DELIVERY_ORDER,
	get_order_status,
	get_precision,
	set_quantities_on_doc,
)


# ----------------------------------------------------------------------
# hooks.py entry points
# ----------------------------------------------------------------------
def validate(doc, method=None):
	validate_against_purchase_order(doc)
	set_quantities_on_doc(doc)


# ----------------------------------------------------------------------
# Create Delivery Note
# ----------------------------------------------------------------------
@frappe.whitelist()
def get_delivery_order_items(delivery_order):
	"""Rows of the Delivery Order with live delivered and pending quantities."""
	frappe.has_permission(DELIVERY_ORDER, "read", doc=delivery_order, throw=True)
	return get_order_status(delivery_order)


@frappe.whitelist()
def make_delivery_note(source_name, items=None, customer=None):
	"""Unsaved Delivery Note against a submitted Delivery Order.

	items: JSON list of {"name": order row name, "qty": qty to deliver}; rows left out or with no
	quantity are skipped. Without items every row's full pending quantity is taken.
	Quantities are checked against the pending quantity here and again when the note is saved.
	"""
	order = frappe.get_doc(DELIVERY_ORDER, source_name)
	order.check_permission("read")
	frappe.has_permission("Delivery Note", "create", throw=True)

	if order.docstatus != 1:
		frappe.throw(_("Submit the Delivery Order first."))

	status = get_order_status(order.name)
	precision = get_precision()
	if status.pending_qty <= 0:
		frappe.throw(
			_("Delivery Order {0} is already fully delivered.").format(
				get_link_to_form(DELIVERY_ORDER, order.name)
			)
		)

	if isinstance(items, str):
		items = json.loads(items)
	wanted = (
		{d.get("name"): flt(d.get("qty")) for d in items}
		if items
		else {r.name: r.pending_qty for r in status.rows}
	)

	dn = frappe.new_doc("Delivery Note")
	dn.company = order.company
	dn.posting_date = nowdate()
	dn.custom_delivery_out = order.name
	if customer:
		dn.customer = customer

	for row in status.rows:
		qty = rounded(wanted.get(row.name, 0), precision)
		if qty <= 0:
			continue
		if rounded(qty - row.pending_qty, precision) > 0:
			frappe.throw(
				_("Row #{0} {1}: quantity {2} is more than the pending quantity {3}.").format(
					row.idx, frappe.bold(row.item_code), qty, frappe.bold(row.pending_qty)
				),
				title=_("Over Delivery"),
			)
		dn.append(
			"items",
			{
				"item_code": row.item_code,
				"item_name": row.item_name,
				"qty": qty,
				"uom": row.uom,
				"stock_uom": row.stock_uom,
				"conversion_factor": flt(row.conversion_factor) or 1,
				"warehouse": row.warehouse,
				"custom_delivery_order": order.name,
				"custom_delivery_order_item": row.name,
			},
		)

	if not dn.get("items"):
		frappe.throw(_("Enter a quantity to deliver for at least one item."))

	if dn.get("customer"):
		# fills price list, addresses, taxes and item rates exactly like a mapped document
		dn.run_method("set_missing_values")
		dn.run_method("calculate_taxes_and_totals")

	return dn


# ----------------------------------------------------------------------
# Create Payment
# ----------------------------------------------------------------------
@frappe.whitelist()
def make_payment_entry(delivery_order):
	"""Payment Entry to the supplier for the Delivery Order's grand total, against its
	Purchase Order. Returns the existing entry when the Delivery Order already has one."""
	order = frappe.get_doc(DELIVERY_ORDER, delivery_order)
	order.check_permission("read")

	if not order.get("purchase_order"):
		frappe.throw(_("This Delivery Order is not linked to a Purchase Order."))

	existing = frappe.db.exists("Payment Entry", {"custom_delivery_order": order.name})
	if existing:
		return existing

	frappe.has_permission("Payment Entry", "create", throw=True)
	po = frappe.get_doc("Purchase Order", order.purchase_order)
	abbr = frappe.get_cached_value("Company", po.company, "abbr")
	amount = flt(order.get("grand_total"))

	pe = frappe.new_doc("Payment Entry")
	naming_series = f"BANK-{abbr}-.YYYY.-"
	if naming_series in (pe.meta.get_field("naming_series").options or "").split("\n"):
		pe.naming_series = naming_series
	pe.payment_type = "Pay"
	pe.party_type = "Supplier"
	pe.party = po.supplier
	pe.company = po.company
	pe.paid_from = get_account(po.company, f"Cash - {abbr}", "default_cash_account")
	pe.paid_from_account_currency = "INR"
	pe.paid_to = get_account(po.company, f"Creditors - {abbr}", "default_payable_account")
	pe.paid_to_account_currency = "INR"
	pe.paid_amount = amount
	pe.received_amount = amount
	pe.custom_delivery_order = order.name
	pe.append(
		"references",
		{
			"reference_doctype": "Purchase Order",
			"reference_name": po.name,
			"total_amount": po.grand_total,
			"outstanding_amount": po.grand_total,
			"allocated_amount": amount,
		},
	)
	pe.insert()
	return pe.name


def get_account(company, preferred, company_default_field):
	"""The account the Server Script used when it exists, else the company default."""
	if frappe.db.exists("Account", {"name": preferred, "company": company}):
		return preferred
	return frappe.get_cached_value("Company", company, company_default_field)
