# Copyright (c) 2026, Reformiqo and contributors
# For license information, please see license.txt

"""Bring existing data into the Delivery Order flow.

1. Create the custom fields (after_migrate runs only after the patches).
2. Link the rows of existing Delivery Notes that name a Delivery Order in their header to the
   Delivery Order rows, by item code - the same allocation new notes get on save. Documents
   are not re-saved; only the two link fields are written.
3. Recompute Delivered / Pending Qty and the delivery status of every submitted Delivery Order.

Existing Purchase Receipts are left as they are.
"""

import frappe

from palriwal.palriwal.delivery_order.custom_fields import DELIVERY_ORDER, setup_custom_fields
from palriwal.palriwal.delivery_order.qty_math import allocate
from palriwal.palriwal.delivery_order.quantities import (
	get_delivered_qty_map,
	get_order_rows,
	get_precision,
	update_delivery_order,
)


def execute():
	if not frappe.db.exists("DocType", DELIVERY_ORDER):
		return
	if not frappe.db.has_column("Delivery Note", "custom_delivery_out"):
		return

	setup_custom_fields()
	precision = get_precision()

	notes = frappe.get_all(
		"Delivery Note",
		filters={"custom_delivery_out": ["is", "set"], "docstatus": ["<", 2]},
		fields=["name", "custom_delivery_out"],
		order_by="posting_date asc, creation asc",  # earlier notes take the earlier rows
	)
	for note in notes:
		link_note_rows(note, precision)

	for delivery_order in frappe.get_all(DELIVERY_ORDER, filters={"docstatus": 1}, pluck="name"):
		update_delivery_order(delivery_order)


def link_note_rows(note, precision):
	order_rows = get_order_rows(note.custom_delivery_out)
	if not order_rows:
		return
	valid = {r.name for r in order_rows}
	note_rows = frappe.get_all(
		"Delivery Note Item",
		filters={"parent": note.name, "parenttype": "Delivery Note"},
		fields=["name", "item_code", "qty", "custom_delivery_order", "custom_delivery_order_item"],
		order_by="idx asc",
	)
	already = get_delivered_qty_map(note.custom_delivery_out, order_rows, note.name)
	allocation = allocate(
		[
			{
				"key": r.name,
				"item_code": r.item_code,
				"qty": abs(r.qty or 0),
				"linked": r.custom_delivery_order_item
				if r.custom_delivery_order == note.custom_delivery_out
				and r.custom_delivery_order_item in valid
				else None,
			}
			for r in note_rows
		],
		[{"name": r.name, "item_code": r.item_code, "qty": r.qty} for r in order_rows],
		already,
		precision,
	)
	for row in note_rows:
		target = allocation.get(row.name)
		frappe.db.set_value(
			"Delivery Note Item",
			row.name,
			{
				"custom_delivery_order": note.custom_delivery_out if target else None,
				"custom_delivery_order_item": target,
			},
			update_modified=False,
		)
