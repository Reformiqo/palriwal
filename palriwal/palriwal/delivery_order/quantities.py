# Copyright (c) 2026, Reformiqo and contributors
# For license information, please see license.txt

"""Delivered / Pending quantities of a Delivery Order, always recomputed from the submitted
Delivery Notes (never incremented), so submit, cancel, return and amend all converge on the
same numbers.
"""

from collections import defaultdict

import frappe
from frappe.utils import cint, flt

from palriwal.palriwal.delivery_order.qty_math import DEFAULT_PRECISION, pending_qty, rounded, summarise

DELIVERY_ORDER = "Delivery Order"


def get_precision():
	return cint(frappe.db.get_single_value("System Settings", "float_precision")) or DEFAULT_PRECISION


def get_order_rows(delivery_order):
	"""The Delivery Order Item rows (Purchase Order Item rows parented by the Delivery Order)."""
	return frappe.get_all(
		"Purchase Order Item",
		filters={"parent": delivery_order, "parenttype": DELIVERY_ORDER, "parentfield": "items"},
		fields=[
			"name",
			"idx",
			"item_code",
			"item_name",
			"qty",
			"uom",
			"stock_uom",
			"conversion_factor",
			"warehouse",
			"rate",
		],
		order_by="idx asc",
	)


def qty_in_order_uom(note_row, order_row):
	"""Delivery Note row quantity expressed in the Delivery Order row's UOM."""
	if not note_row.get("uom") or note_row.get("uom") == order_row.get("uom"):
		return flt(note_row.get("qty"))
	return flt(note_row.get("stock_qty")) / (flt(order_row.get("conversion_factor")) or 1)


def get_delivered_qty_map(delivery_order, order_rows=None, exclude_delivery_note=None):
	"""{order row name: qty delivered by submitted Delivery Notes}; returns count negative."""
	if order_rows is None:
		order_rows = get_order_rows(delivery_order)
	by_name = {r.name: r for r in order_rows}

	note_rows = frappe.db.sql(
		"""
		select dni.custom_delivery_order_item, dni.qty, dni.stock_qty, dni.uom
		from `tabDelivery Note Item` dni
		inner join `tabDelivery Note` dn on dn.name = dni.parent
		where dn.docstatus = 1
			and dni.custom_delivery_order = %(delivery_order)s
			and ifnull(dni.custom_delivery_order_item, '') != ''
			and dn.name != %(exclude)s
		""",
		{"delivery_order": delivery_order, "exclude": exclude_delivery_note or ""},
		as_dict=True,
	)

	delivered = defaultdict(float)
	for row in note_rows:
		order_row = by_name.get(row.custom_delivery_order_item)
		if order_row:
			delivered[order_row.name] += qty_in_order_uom(row, order_row)
	return delivered


def get_order_status(delivery_order, exclude_delivery_note=None):
	"""Per-row and total delivered / pending quantities, computed live."""
	precision = get_precision()
	order_rows = get_order_rows(delivery_order)
	delivered = get_delivered_qty_map(delivery_order, order_rows, exclude_delivery_note)

	rows = []
	for row in order_rows:
		row_delivered = rounded(delivered.get(row.name, 0), precision)
		rows.append(
			frappe._dict(
				row,
				delivered_qty=row_delivered,
				pending_qty=pending_qty(row.qty, row_delivered, precision),
			)
		)
	return frappe._dict(rows=rows, **summarise(order_rows, delivered, precision))


def update_delivery_order(delivery_order):
	"""Write the live quantities onto the (submitted) Delivery Order and its rows."""
	if not delivery_order or not frappe.db.exists(DELIVERY_ORDER, delivery_order):
		return

	status = get_order_status(delivery_order)
	for row in status.rows:
		frappe.db.set_value(
			"Purchase Order Item",
			row.name,
			{"custom_delivered_qty": row.delivered_qty, "custom_pending_qty": row.pending_qty},
			update_modified=False,
		)

	frappe.db.set_value(
		DELIVERY_ORDER,
		delivery_order,
		{
			"custom_total_delivered_qty": status.delivered_qty,
			"custom_total_pending_qty": status.pending_qty,
			"custom_delivery_status": status.status,
		},
		update_modified=False,
	)
	return status


def set_quantities_on_doc(doc):
	"""Same numbers on an in-memory Delivery Order (its own validate / submit)."""
	precision = get_precision()
	rows = [r for r in doc.get("items") or []]
	delivered = get_delivered_qty_map(doc.name, rows) if not doc.is_new() else {}

	for row in rows:
		row.custom_delivered_qty = rounded(delivered.get(row.name, 0), precision)
		row.custom_pending_qty = pending_qty(row.qty, row.custom_delivered_qty, precision)

	summary = summarise([{"name": r.name, "qty": r.qty} for r in rows], delivered, precision)
	doc.custom_total_delivered_qty = summary["delivered_qty"]
	doc.custom_total_pending_qty = summary["pending_qty"]
	doc.custom_delivery_status = summary["status"]
