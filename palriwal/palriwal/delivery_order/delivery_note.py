# Copyright (c) 2026, Reformiqo and contributors
# For license information, please see license.txt

"""Delivery Note side of the Delivery Order flow (hooks.py doc_events).

A Delivery Note is in the flow when its header ``custom_delivery_out`` names a Delivery Order.
Then, on every save:
    * each item row is linked to the Delivery Order row it delivers (custom_delivery_order /
      custom_delivery_order_item); items that are not on the Delivery Order stay unlinked
    * the linked quantity may not exceed the row's pending quantity (returns excepted)
On submit the Delivery Order quantities are refreshed and a draft Purchase Receipt is made for
exactly the linked Delivery Note quantity. On cancel the Purchase Receipts made from the note
are cancelled (drafts deleted) and the Delivery Order quantities refreshed.

Replaces the "Creating purchase receipt on delivery note submission ..." and "Cancelling
purchase receipt when delivery note is cancelled" Server Scripts, which copied the full
Delivery Order quantity into the Purchase Receipt.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, flt, get_link_to_form

from palriwal.palriwal.delivery_order.qty_math import allocate, over_deliveries, rounded
from palriwal.palriwal.delivery_order.quantities import (
	DELIVERY_ORDER,
	get_delivered_qty_map,
	get_order_rows,
	get_precision,
	qty_in_order_uom,
	update_delivery_order,
)

# Stock is received into this warehouse ("Stores - <company abbr>") when it exists, else into
# the Purchase Order row's warehouse. "Stores - JAT" is what the Server Script hard-coded.
RECEIPT_WAREHOUSE_PREFIX = "Stores"

# Tax row fields copied from the Purchase Order onto the Purchase Receipt
TAX_FIELDS = (
	"category",
	"add_deduct_tax",
	"charge_type",
	"row_id",
	"account_head",
	"description",
	"rate",
	"cost_center",
	"included_in_print_rate",
)


# ----------------------------------------------------------------------
# hooks.py entry points
# ----------------------------------------------------------------------
def validate(doc, method=None):
	delivery_order = doc.get("custom_delivery_out")
	if not delivery_order:
		for row in doc.get("items"):
			row.custom_delivery_order = None
			row.custom_delivery_order_item = None
		return

	order = frappe.db.get_value(
		DELIVERY_ORDER, delivery_order, ["name", "docstatus", "company"], as_dict=True
	)
	if not order:
		frappe.throw(_("Delivery Order {0} does not exist.").format(frappe.bold(delivery_order)))
	if order.docstatus != 1:
		frappe.throw(
			_("Delivery Order {0} must be submitted before a Delivery Note can be made against it.").format(
				get_link_to_form(DELIVERY_ORDER, delivery_order)
			)
		)
	if order.company and doc.company and order.company != doc.company:
		frappe.throw(
			_("Delivery Order {0} belongs to company {1}, not {2}.").format(
				get_link_to_form(DELIVERY_ORDER, delivery_order), order.company, doc.company
			)
		)

	order_rows = get_order_rows(delivery_order)
	is_return = cint(doc.get("is_return"))
	already = {} if is_return else get_delivered_qty_map(delivery_order, order_rows, doc.name)

	link_items(doc, delivery_order, order_rows, already)
	if not is_return:
		validate_pending_qty(doc, delivery_order, order_rows, already)


def on_submit(doc, method=None):
	delivery_order = doc.get("custom_delivery_out")
	if not delivery_order:
		return
	update_delivery_order(delivery_order)
	if not cint(doc.get("is_return")):
		create_purchase_receipt(doc)


def on_cancel(doc, method=None):
	delivery_order = doc.get("custom_delivery_out")
	if not delivery_order:
		return
	cancel_purchase_receipts(doc)
	update_delivery_order(delivery_order)


# ----------------------------------------------------------------------
# validation
# ----------------------------------------------------------------------
def link_items(doc, delivery_order, order_rows, already):
	precision = get_precision()
	valid = {r.name for r in order_rows}
	note_rows = [
		{
			"key": row.idx,
			"item_code": row.item_code,
			"qty": abs(flt(row.qty)),
			"linked": row.get("custom_delivery_order_item")
			if row.get("custom_delivery_order") == delivery_order
			and row.get("custom_delivery_order_item") in valid
			else None,
		}
		for row in doc.get("items")
	]
	allocation = allocate(
		note_rows,
		[{"name": r.name, "item_code": r.item_code, "qty": r.qty} for r in order_rows],
		already,
		precision,
	)
	for row in doc.get("items"):
		target = allocation.get(row.idx)
		row.custom_delivery_order = delivery_order if target else None
		row.custom_delivery_order_item = target


def validate_pending_qty(doc, delivery_order, order_rows, already):
	precision = get_precision()
	by_name = {r.name: r for r in order_rows}
	requested = defaultdict(float)
	for row in doc.get("items"):
		order_row = by_name.get(row.get("custom_delivery_order_item"))
		if order_row:
			requested[order_row.name] += qty_in_order_uom(row, order_row)

	problems = over_deliveries(requested, order_rows, already, precision)
	if not problems:
		return

	link = get_link_to_form(DELIVERY_ORDER, delivery_order)
	if all(p["pending"] <= 0 for p in problems) and all(
		rounded(r.qty - already.get(r.name, 0), precision) <= 0 for r in order_rows
	):
		frappe.throw(
			_("Delivery Order {0} is already fully delivered. No further quantity can be delivered.").format(
				link
			),
			title=_("Over Delivery"),
		)

	lines = [
		_(
			"Row #{0} {1}: Delivery Order Qty {2}, Already Delivered {3}, Pending {4}, This Delivery Note {5} {6}"
		).format(
			p["row"].idx,
			frappe.bold(p["row"].item_code),
			p["ordered"],
			p["delivered"],
			frappe.bold(p["pending"]),
			frappe.bold(p["requested"]),
			p["row"].uom or "",
		)
		for p in problems
	]
	frappe.throw(
		_("Delivery Note quantity is more than the pending quantity of Delivery Order {0}:").format(link)
		+ "<br><br>"
		+ "<br>".join(lines),
		title=_("Over Delivery"),
	)


# ----------------------------------------------------------------------
# Purchase Receipt
# ----------------------------------------------------------------------
def get_existing_purchase_receipt(delivery_note):
	return frappe.db.get_value(
		"Purchase Receipt",
		{"custom_delivery_note": delivery_note, "docstatus": ["<", 2], "is_return": 0},
		"name",
	)


def create_purchase_receipt(doc):
	"""Draft Purchase Receipt for exactly the Delivery Order quantity this note delivered."""
	existing = get_existing_purchase_receipt(doc.name)
	if existing:
		frappe.msgprint(
			_("Purchase Receipt {0} already exists for Delivery Note {1}.").format(
				get_link_to_form("Purchase Receipt", existing), doc.name
			)
		)
		return existing

	order = frappe.get_doc(DELIVERY_ORDER, doc.custom_delivery_out)
	if not order.get("purchase_order"):
		frappe.throw(
			_("Purchase Order is missing in Delivery Order {0}.").format(
				get_link_to_form(DELIVERY_ORDER, order.name)
			)
		)
	po = frappe.get_doc("Purchase Order", order.purchase_order)
	order_rows = {r.name: r for r in order.get("items")}

	pr = frappe.new_doc("Purchase Receipt")
	pr.supplier = po.supplier
	pr.company = doc.company
	pr.posting_date = doc.posting_date
	pr.posting_time = doc.posting_time
	pr.set_posting_time = 1
	pr.currency = po.currency
	pr.conversion_rate = po.conversion_rate
	pr.custom_delivery_note = doc.name
	pr.custom_delivery_out = order.name
	if pr.meta.has_field("custom_purchase_order"):
		pr.custom_purchase_order = po.name

	for row in doc.get("items"):
		order_row = order_rows.get(row.get("custom_delivery_order_item"))
		if not order_row or row.get("custom_delivery_order") != order.name:
			continue
		po_item = next((i for i in po.items if i.item_code == order_row.item_code), None)
		if not po_item:
			frappe.throw(
				_("Item {0} not found in Purchase Order {1}.").format(
					frappe.bold(order_row.item_code), get_link_to_form("Purchase Order", po.name)
				)
			)
		pr.append(
			"items",
			{
				"item_code": order_row.item_code,
				"qty": qty_in_order_uom(row, order_row),
				"uom": order_row.uom,
				"conversion_factor": flt(order_row.conversion_factor) or flt(po_item.conversion_factor) or 1,
				"rate": po_item.rate,
				"warehouse": get_receipt_warehouse(doc.company, po_item),
				"purchase_order": po.name,
				"purchase_order_item": po_item.name,
				"custom_delivery_note_item": row.name,
			},
		)

	if not pr.get("items"):
		frappe.msgprint(
			_(
				"No item of Delivery Note {0} is on Delivery Order {1}; no Purchase Receipt was created."
			).format(doc.name, order.name)
		)
		return None

	copy_taxes(po, pr)
	pr.insert(ignore_permissions=True)

	total = sum(flt(i.qty) for i in pr.items)
	frappe.msgprint(
		_("Purchase Receipt {0} created in Draft for {1} {2}.").format(
			get_link_to_form("Purchase Receipt", pr.name), frappe.bold(total), pr.items[0].uom or ""
		),
		indicator="green",
		alert=True,
	)
	return pr.name


def copy_taxes(po, pr):
	if po.get("taxes_and_charges"):
		pr.taxes_and_charges = po.taxes_and_charges

	# the TCS engine recomputes its own row on the receipt from these two fields
	for field in ("custom_apply_tcs", "custom_tcs_category"):
		if pr.meta.has_field(field) and po.get(field):
			pr.set(field, po.get(field))

	po_total = flt(po.get("total"))
	pr_total = sum(flt(i.qty) * flt(i.rate) for i in pr.items)
	for tax in po.get("taxes") or []:
		if cint(tax.get("custom_is_tcs_row")):
			continue
		row = {field: tax.get(field) for field in TAX_FIELDS if tax.get(field) is not None}
		if tax.charge_type == "Actual":
			# a fixed charge follows the share of the order that is being received
			row["tax_amount"] = flt(tax.tax_amount) * pr_total / po_total if po_total else 0
		pr.append("taxes", row)


def get_receipt_warehouse(company, po_item):
	abbr = frappe.get_cached_value("Company", company, "abbr")
	warehouse = f"{RECEIPT_WAREHOUSE_PREFIX} - {abbr}"
	if frappe.db.exists("Warehouse", {"name": warehouse, "company": company, "is_group": 0}):
		return warehouse
	return po_item.warehouse


def cancel_purchase_receipts(doc):
	receipts = frappe.get_all(
		"Purchase Receipt",
		filters={"custom_delivery_note": doc.name, "docstatus": ["<", 2]},
		fields=["name", "docstatus", "is_return"],
		order_by="is_return desc, creation desc",  # returns first, they block the receipt
	)
	for receipt in receipts:
		if receipt.docstatus == 1:
			frappe.get_doc("Purchase Receipt", receipt.name).cancel()
			frappe.msgprint(_("Purchase Receipt {0} cancelled.").format(receipt.name), alert=True)
		else:
			frappe.delete_doc("Purchase Receipt", receipt.name, ignore_permissions=True)
			frappe.msgprint(_("Draft Purchase Receipt {0} deleted.").format(receipt.name), alert=True)


@frappe.whitelist()
def make_purchase_receipt(delivery_note):
	"""'Create Purchase Receipt' button: the receipt of a submitted note, created if missing."""
	doc = frappe.get_doc("Delivery Note", delivery_note)
	doc.check_permission("read")
	frappe.has_permission("Purchase Receipt", "create", throw=True)

	if doc.docstatus != 1:
		frappe.throw(_("Submit the Delivery Note first."))
	if not doc.get("custom_delivery_out"):
		frappe.throw(_("Delivery Note {0} is not linked to a Delivery Order.").format(doc.name))
	if cint(doc.get("is_return")):
		frappe.throw(_("Make the return from the Purchase Receipt itself."))

	return create_purchase_receipt(doc)
