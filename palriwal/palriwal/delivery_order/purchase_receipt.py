# Copyright (c) 2026, Reformiqo and contributors
# For license information, please see license.txt

"""Purchase Receipt side of the Delivery Order flow (hooks.py doc_events).

A receipt made from a Delivery Note (``custom_delivery_note``) may not receive more of an item
than the note delivered, counting every other open receipt of the same note, and can only be
submitted while the note is submitted. Items that are not on the note (e.g. Plot Charges) are
not checked. Return receipts and receipts of return notes are not checked.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, flt, get_link_to_form

from palriwal.palriwal.delivery_order.qty_math import rounded
from palriwal.palriwal.delivery_order.quantities import get_precision


def validate(doc, method=None):
	delivery_note = doc.get("custom_delivery_note")
	if not delivery_note or cint(doc.get("is_return")):
		return

	note = frappe.db.get_value("Delivery Note", delivery_note, ["docstatus", "is_return"], as_dict=True)
	if not note or cint(note.is_return):
		# free-text field that does not name a Delivery Note, or a return note (the app makes no
		# receipt for those) - nothing to compare
		return
	if doc.docstatus == 1 and note.docstatus != 1:
		frappe.throw(
			_("Delivery Note {0} is not submitted, so this Purchase Receipt cannot be submitted.").format(
				get_link_to_form("Delivery Note", delivery_note)
			)
		)

	delivered = get_delivery_note_stock_qty(delivery_note)
	received = get_other_receipts_stock_qty(delivery_note, doc.name)
	for row in doc.get("items"):
		if row.item_code in delivered:
			received[row.item_code] += (flt(row.qty) + flt(row.rejected_qty)) * (
				flt(row.conversion_factor) or 1
			)

	precision = get_precision()
	lines = []
	for item_code, qty in received.items():
		if item_code in delivered and rounded(qty - delivered[item_code], precision) > 0:
			lines.append(
				_("{0}: received {1}, Delivery Note {2} (stock UOM)").format(
					frappe.bold(item_code),
					frappe.bold(rounded(qty, precision)),
					frappe.bold(rounded(delivered[item_code], precision)),
				)
			)
	if lines:
		frappe.throw(
			_(
				"Purchase Receipt quantity must not be more than the quantity of Delivery Note {0}"
				" (other open Purchase Receipts of the same note included):"
			).format(get_link_to_form("Delivery Note", delivery_note))
			+ "<br><br>"
			+ "<br>".join(lines),
			title=_("Quantity more than Delivery Note"),
		)


def get_delivery_note_stock_qty(delivery_note):
	rows = frappe.get_all(
		"Delivery Note Item",
		filters={"parent": delivery_note, "parenttype": "Delivery Note"},
		fields=["item_code", "stock_qty"],
	)
	qty = defaultdict(float)
	for row in rows:
		qty[row.item_code] += flt(row.stock_qty)
	return qty


def get_other_receipts_stock_qty(delivery_note, exclude):
	rows = frappe.db.sql(
		"""
		select pri.item_code, pri.qty, pri.rejected_qty, pri.conversion_factor
		from `tabPurchase Receipt Item` pri
		inner join `tabPurchase Receipt` pr on pr.name = pri.parent
		where pr.custom_delivery_note = %s and pr.docstatus < 2 and pr.is_return = 0 and pr.name != %s
		""",
		(delivery_note, exclude or ""),
		as_dict=True,
	)
	qty = defaultdict(float)
	for row in rows:
		qty[row.item_code] += (flt(row.qty) + flt(row.rejected_qty)) * (flt(row.conversion_factor) or 1)
	return qty
