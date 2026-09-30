# Copyright (c) 2026, Reformiqo and contributors
# For license information, please see license.txt

"""Delivery Order Tracker: Purchase Order -> Delivery Order -> Delivery Note -> Purchase Receipt.

Two views:
    Transaction Detail      one line per Delivery Order row x Delivery Note row x Purchase
                            Receipt row. Quantities of a document appear on its first line only,
                            so the total row adds up.
    Delivery Order Summary  one line per Delivery Order row with delivered / pending quantity,
                            Delivery Note and Purchase Receipt counts, quantities and names.

Submitted Delivery Orders and Delivery Notes; draft and submitted Purchase Receipts (the
receipt is made in draft). Delivery Note returns show with negative quantity.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt

from palriwal.palriwal.delivery_order.qty_math import rounded

VIEW_SUMMARY = "Delivery Order Summary"
PR_NOT_CREATED = "Not Created"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if filters.from_date and filters.to_date and filters.from_date > filters.to_date:
		frappe.throw(_("From Date must be before To Date"))

	order_rows = get_order_rows(filters)
	note_rows = get_note_rows(filters, order_rows)
	receipt_rows = get_receipt_rows(note_rows)
	po_items = get_po_items(order_rows)

	if filters.view == VIEW_SUMMARY:
		columns = get_summary_columns()
		data = get_summary_data(filters, order_rows, note_rows, receipt_rows, po_items)
	else:
		columns = get_detail_columns()
		data = get_detail_data(filters, order_rows, note_rows, receipt_rows, po_items)

	return columns, data, None, None, get_report_summary(data)


# ----------------------------------------------------------------------
# data
# ----------------------------------------------------------------------
def get_order_rows(filters):
	conditions = ["dord.docstatus = 1", "doi.parenttype = 'Delivery Order'"]
	for field, column in (
		("company", "dord.company"),
		("purchase_order", "dord.purchase_order"),
		("delivery_order", "dord.name"),
		("supplier", "dord.supplier"),
		("item_code", "doi.item_code"),
		("delivery_status", "dord.custom_delivery_status"),
	):
		if filters.get(field):
			conditions.append(f"{column} = %({field})s")
	if filters.from_date:
		conditions.append("dord.transaction_date >= %(from_date)s")
	if filters.to_date:
		conditions.append("dord.transaction_date <= %(to_date)s")
	if filters.pending_only:
		conditions.append("ifnull(doi.custom_pending_qty, 0) > 0")

	return frappe.db.sql(
		f"""
		select
			dord.name as delivery_order, dord.transaction_date as do_date, dord.required_by,
			dord.purchase_order, dord.supplier, dord.supplier_name, dord.company,
			dord.custom_delivery_status as delivery_status,
			doi.name as order_row, doi.idx, doi.item_code, doi.item_name, doi.qty as do_qty, doi.uom,
			doi.warehouse as do_warehouse, doi.custom_delivered_qty as delivered_qty,
			doi.custom_pending_qty as pending_qty
		from `tabDelivery Order` dord
		inner join `tabPurchase Order Item` doi on doi.parent = dord.name
		where {" and ".join(conditions)}
		order by dord.transaction_date desc, dord.name desc, doi.idx asc
		""",
		filters,
		as_dict=True,
	)


def get_note_rows(filters, order_rows):
	"""{order row name: [Delivery Note rows]}"""
	orders = list({r.delivery_order for r in order_rows})
	if not orders:
		return {}
	values = {"orders": tuple(orders), "customer": filters.customer}
	customer_condition = "and dn.customer = %(customer)s" if filters.customer else ""
	rows = frappe.db.sql(
		f"""
		select
			dn.name as delivery_note, dn.posting_date as dn_date, dn.customer, dn.customer_name,
			dn.status as dn_status, dn.is_return,
			dni.name as note_row, dni.item_code, dni.qty as dn_qty, dni.warehouse as dn_warehouse,
			dni.custom_delivery_order_item as order_row
		from `tabDelivery Note Item` dni
		inner join `tabDelivery Note` dn on dn.name = dni.parent
		where dn.docstatus = 1 and dni.custom_delivery_order in %(orders)s {customer_condition}
		order by dn.posting_date asc, dn.name asc, dni.idx asc
		""",
		values,
		as_dict=True,
	)
	by_order_row = defaultdict(list)
	for row in rows:
		by_order_row[row.order_row].append(row)
	return by_order_row


def get_receipt_rows(note_rows):
	"""{Delivery Note row name: [Purchase Receipt rows]}"""
	notes = {}
	for rows in note_rows.values():
		for row in rows:
			notes.setdefault(row.delivery_note, []).append(row)
	if not notes:
		return {}

	receipts = frappe.db.sql(
		"""
		select
			pr.name as purchase_receipt, pr.posting_date as pr_date, pr.status as pr_status,
			pr.docstatus as pr_docstatus, pr.custom_delivery_note as delivery_note,
			pri.item_code, pri.qty + ifnull(pri.rejected_qty, 0) as pr_qty,
			pri.warehouse as pr_warehouse, pri.custom_delivery_note_item as note_row
		from `tabPurchase Receipt Item` pri
		inner join `tabPurchase Receipt` pr on pr.name = pri.parent
		where pr.docstatus < 2 and pr.is_return = 0 and pr.custom_delivery_note in %(notes)s
		order by pr.posting_date asc, pr.name asc, pri.idx asc
		""",
		{"notes": tuple(notes)},
		as_dict=True,
	)

	by_note_row = defaultdict(list)
	for receipt in receipts:
		note_row = receipt.note_row
		if not note_row or note_row not in {r.note_row for r in notes[receipt.delivery_note]}:
			# receipts made before the row link existed: first note row of the same item
			note_row = next(
				(r.note_row for r in notes[receipt.delivery_note] if r.item_code == receipt.item_code), None
			)
		if note_row:
			by_note_row[note_row].append(receipt)
	return by_note_row


def get_po_items(order_rows):
	"""{(purchase order, item code): {po_date, po_status, ordered_qty, received_qty}}"""
	orders = list({r.purchase_order for r in order_rows if r.purchase_order})
	if not orders:
		return {}
	rows = frappe.db.sql(
		"""
		select po.name, po.transaction_date, po.status, poi.item_code,
			sum(poi.qty) as ordered_qty, sum(poi.received_qty) as received_qty
		from `tabPurchase Order Item` poi
		inner join `tabPurchase Order` po on po.name = poi.parent
		where poi.parenttype = 'Purchase Order' and po.name in %(orders)s
		group by po.name, po.transaction_date, po.status, poi.item_code
		""",
		{"orders": tuple(orders)},
		as_dict=True,
	)
	return {
		(r.name, r.item_code): frappe._dict(
			po_date=r.transaction_date,
			po_status=r.status,
			ordered_qty=r.ordered_qty,
			received_qty=r.received_qty,
		)
		for r in rows
	}


def pr_status_of(receipts):
	if not receipts:
		return PR_NOT_CREATED
	statuses = {"Draft" if r.pr_docstatus == 0 else "Submitted" for r in receipts}
	return statuses.pop() if len(statuses) == 1 else "Partly Submitted"


def order_values(order, po_items, first):
	po = po_items.get((order.purchase_order, order.item_code), frappe._dict())
	return {
		"purchase_order": order.purchase_order,
		"po_date": po.po_date,
		"po_status": po.po_status,
		"supplier": order.supplier,
		"supplier_name": order.supplier_name,
		"item_code": order.item_code,
		"item_name": order.item_name,
		"ordered_qty": flt(po.ordered_qty) if first else None,
		"delivery_order": order.delivery_order,
		"do_date": order.do_date,
		"required_by": order.required_by,
		"delivery_status": order.delivery_status,
		"do_qty": flt(order.do_qty) if first else None,
		"delivered_qty": flt(order.delivered_qty) if first else None,
		"pending_qty": flt(order.pending_qty) if first else None,
		"uom": order.uom,
		"do_warehouse": order.do_warehouse,
		"company": order.company,
	}


def keep_order_row(filters, notes):
	"""Customer and receipt status filters only keep Delivery Order rows that have a match."""
	return not (filters.customer or filters.pr_status) or bool(notes)


def filter_notes(filters, notes, receipt_rows):
	if not filters.pr_status:
		return notes
	return [n for n in notes if pr_status_of(receipt_rows.get(n.note_row)) == filters.pr_status]


def get_detail_data(filters, order_rows, note_rows, receipt_rows, po_items):
	data = []
	for order in order_rows:
		notes = filter_notes(filters, note_rows.get(order.order_row, []), receipt_rows)
		if not keep_order_row(filters, notes):
			continue
		if not notes:
			data.append(order_values(order, po_items, True))
			continue

		first_line_of_order = True
		for note in notes:
			receipts = receipt_rows.get(note.note_row, [])
			received = sum(flt(r.pr_qty) for r in receipts)
			note_values = {
				"delivery_note": note.delivery_note,
				"dn_date": note.dn_date,
				"customer": note.customer,
				"customer_name": note.customer_name,
				"dn_status": _("Return") if note.is_return else note.dn_status,
				"dn_warehouse": note.dn_warehouse,
				"pr_status": pr_status_of(receipts) if not note.is_return else None,
			}
			for i, receipt in enumerate(receipts or [None]):
				line = order_values(order, po_items, first_line_of_order)
				line.update(note_values)
				if i == 0:
					line["dn_qty"] = flt(note.dn_qty)
					if not note.is_return:
						line["not_received_qty"] = rounded(flt(note.dn_qty) - received)
				if receipt:
					line.update(
						{
							"purchase_receipt": receipt.purchase_receipt,
							"pr_date": receipt.pr_date,
							"pr_row_status": receipt.pr_status,
							"pr_qty": flt(receipt.pr_qty),
							"pr_warehouse": receipt.pr_warehouse,
						}
					)
				data.append(line)
				first_line_of_order = False
	return data


def get_summary_data(filters, order_rows, note_rows, receipt_rows, po_items):
	data = []
	for order in order_rows:
		notes = filter_notes(filters, note_rows.get(order.order_row, []), receipt_rows)
		if not keep_order_row(filters, notes):
			continue
		receipts = [r for n in notes for r in receipt_rows.get(n.note_row, [])]
		dn_qty = sum(flt(n.dn_qty) for n in notes)
		pr_qty = sum(flt(r.pr_qty) for r in receipts)
		line = order_values(order, po_items, True)
		line.update(
			{
				"dn_count": len({n.delivery_note for n in notes}),
				"dn_qty": dn_qty,
				"pr_count": len({r.purchase_receipt for r in receipts}),
				"pr_qty": pr_qty,
				"pr_submitted_qty": sum(flt(r.pr_qty) for r in receipts if r.pr_docstatus == 1),
				"not_received_qty": rounded(sum(flt(n.dn_qty) for n in notes if not n.is_return) - pr_qty),
				"delivery_notes": ", ".join(dict.fromkeys(n.delivery_note for n in notes)),
				"purchase_receipts": ", ".join(dict.fromkeys(r.purchase_receipt for r in receipts)),
			}
		)
		data.append(line)
	return data


def get_report_summary(data):
	do_qty = sum(flt(d.get("do_qty")) for d in data)
	delivered = sum(flt(d.get("delivered_qty")) for d in data)
	pending = sum(flt(d.get("pending_qty")) for d in data)
	received = sum(flt(d.get("pr_qty")) for d in data)
	return [
		{"value": rounded(do_qty), "label": _("Delivery Order Qty"), "datatype": "Float"},
		{
			"value": rounded(delivered),
			"label": _("Delivered Qty"),
			"datatype": "Float",
			"indicator": "Blue",
		},
		{
			"value": rounded(pending),
			"label": _("Pending Qty"),
			"datatype": "Float",
			"indicator": "Orange" if pending > 0 else "Green",
		},
		{
			"value": rounded(received),
			"label": _("Purchase Receipt Qty"),
			"datatype": "Float",
			"indicator": "Green",
		},
	]


# ----------------------------------------------------------------------
# columns
# ----------------------------------------------------------------------
def order_columns():
	return [
		{"label": _("Purchase Order"), "fieldname": "purchase_order", "fieldtype": "Link", "options": "Purchase Order", "width": 160},
		{"label": _("PO Date"), "fieldname": "po_date", "fieldtype": "Date", "width": 95},
		{"label": _("PO Status"), "fieldname": "po_status", "fieldtype": "Data", "width": 110},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 150},
		{"label": _("Supplier Name"), "fieldname": "supplier_name", "fieldtype": "Data", "width": 170},
		{"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 140},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 150},
		{"label": _("Ordered Qty (PO)"), "fieldname": "ordered_qty", "fieldtype": "Float", "width": 120},
		{"label": _("Delivery Order"), "fieldname": "delivery_order", "fieldtype": "Link", "options": "Delivery Order", "width": 130},
		{"label": _("DO Date"), "fieldname": "do_date", "fieldtype": "Date", "width": 95},
		{"label": _("Required By"), "fieldname": "required_by", "fieldtype": "Date", "width": 95},
		{"label": _("Delivery Status"), "fieldname": "delivery_status", "fieldtype": "Data", "width": 130},
		{"label": _("DO Qty"), "fieldname": "do_qty", "fieldtype": "Float", "width": 100},
		{"label": _("Delivered Qty"), "fieldname": "delivered_qty", "fieldtype": "Float", "width": 110},
		{"label": _("Pending Qty"), "fieldname": "pending_qty", "fieldtype": "Float", "width": 105},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Link", "options": "UOM", "width": 70},
		{"label": _("DO Warehouse"), "fieldname": "do_warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 150},
	]  # fmt: skip


def get_detail_columns():
	return [
		*order_columns(),
		{"label": _("Delivery Note"), "fieldname": "delivery_note", "fieldtype": "Link", "options": "Delivery Note", "width": 130},
		{"label": _("DN Date"), "fieldname": "dn_date", "fieldtype": "Date", "width": 95},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 150},
		{"label": _("Customer Name"), "fieldname": "customer_name", "fieldtype": "Data", "width": 170},
		{"label": _("DN Status"), "fieldname": "dn_status", "fieldtype": "Data", "width": 100},
		{"label": _("DN Qty"), "fieldname": "dn_qty", "fieldtype": "Float", "width": 100},
		{"label": _("DN Warehouse"), "fieldname": "dn_warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 150},
		{"label": _("PR Status"), "fieldname": "pr_status", "fieldtype": "Data", "width": 110},
		{"label": _("Purchase Receipt"), "fieldname": "purchase_receipt", "fieldtype": "Link", "options": "Purchase Receipt", "width": 130},
		{"label": _("PR Date"), "fieldname": "pr_date", "fieldtype": "Date", "width": 95},
		{"label": _("PR Document Status"), "fieldname": "pr_row_status", "fieldtype": "Data", "width": 120},
		{"label": _("PR Qty"), "fieldname": "pr_qty", "fieldtype": "Float", "width": 100},
		{"label": _("PR Warehouse"), "fieldname": "pr_warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 130},
		{"label": _("DN Qty without PR"), "fieldname": "not_received_qty", "fieldtype": "Float", "width": 130},
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 140},
	]  # fmt: skip


def get_summary_columns():
	return [
		*order_columns(),
		{"label": _("No. of DNs"), "fieldname": "dn_count", "fieldtype": "Int", "width": 90},
		{"label": _("DN Qty"), "fieldname": "dn_qty", "fieldtype": "Float", "width": 100},
		{"label": _("No. of PRs"), "fieldname": "pr_count", "fieldtype": "Int", "width": 90},
		{"label": _("PR Qty"), "fieldname": "pr_qty", "fieldtype": "Float", "width": 100},
		{"label": _("PR Submitted Qty"), "fieldname": "pr_submitted_qty", "fieldtype": "Float", "width": 125},
		{"label": _("DN Qty without PR"), "fieldname": "not_received_qty", "fieldtype": "Float", "width": 130},
		{"label": _("Delivery Notes"), "fieldname": "delivery_notes", "fieldtype": "Data", "width": 220},
		{"label": _("Purchase Receipts"), "fieldname": "purchase_receipts", "fieldtype": "Data", "width": 220},
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 140},
	]  # fmt: skip
