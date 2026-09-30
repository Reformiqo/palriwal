# Copyright (c) 2026, Reformiqo and contributors
# For license information, please see license.txt

"""Purchase Order -> Delivery Order, ported from the "Get pending qty in dn creation from po - N"
and "Making Delivery Out from PO - N" Server Scripts.

Same rules as the scripts: a Purchase Order item's pending quantity is its quantity less the
quantity on every draft or submitted Delivery Order of the Purchase Order; the Delivery Order
takes the Purchase Order rate and warehouse and gets CGST + SGST (intra-state) or IGST
(inter-state) rows from the item tax template.
"""

import json
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, get_link_to_form, today

from palriwal.palriwal.delivery_order.qty_math import rounded
from palriwal.palriwal.delivery_order.quantities import DELIVERY_ORDER, get_precision


def get_allocated_qty(purchase_order, exclude_delivery_order=None):
	"""{item_code: qty on draft and submitted Delivery Orders of the Purchase Order}."""
	rows = frappe.db.sql(
		"""
		select doi.item_code, doi.qty
		from `tabPurchase Order Item` doi
		inner join `tabDelivery Order` dord on dord.name = doi.parent
		where doi.parenttype = 'Delivery Order' and dord.purchase_order = %s
			and dord.docstatus < 2 and dord.name != %s
		""",
		(purchase_order, exclude_delivery_order or ""),
		as_dict=True,
	)
	allocated = defaultdict(float)
	for row in rows:
		allocated[row.item_code] += flt(row.qty)
	return allocated


def get_ordered_qty(po):
	ordered = defaultdict(float)
	for row in po.items:
		ordered[row.item_code] += flt(row.qty)
	return ordered


@frappe.whitelist()
def get_pending_items(purchase_order):
	"""Purchase Order items with the quantity still available for Delivery Orders."""
	po = frappe.get_doc("Purchase Order", purchase_order)
	po.check_permission("read")
	precision = get_precision()
	ordered = get_ordered_qty(po)
	allocated = get_allocated_qty(po.name)

	result, seen = [], set()
	for row in po.items:
		if row.item_code in seen:
			continue
		seen.add(row.item_code)
		result.append(
			{
				"item_code": row.item_code,
				"item_name": row.item_name,
				"uom": row.uom,
				"ordered_qty": rounded(ordered[row.item_code], precision),
				"allocated_qty": rounded(allocated[row.item_code], precision),
				"pending_qty": rounded(ordered[row.item_code] - allocated[row.item_code], precision),
			}
		)
	return result


def validate_against_purchase_order(doc):
	"""Delivery Order validate: its items may not take more than the Purchase Order has left."""
	if not doc.get("purchase_order"):
		return
	po = frappe.get_doc("Purchase Order", doc.purchase_order)
	if po.docstatus == 2:
		frappe.throw(
			_("Purchase Order {0} is cancelled.").format(get_link_to_form("Purchase Order", po.name))
		)

	precision = get_precision()
	ordered = get_ordered_qty(po)
	allocated = get_allocated_qty(po.name, doc.name)
	this_order = defaultdict(float)
	for row in doc.get("items") or []:
		this_order[row.item_code] += flt(row.qty)

	lines = []
	for item_code, qty in this_order.items():
		if item_code not in ordered:
			continue  # not a Purchase Order item: nothing to measure against
		pending = rounded(ordered[item_code] - allocated[item_code], precision)
		if rounded(qty - pending, precision) > 0:
			lines.append(
				_("{0}: Delivery Order {1}, Purchase Order {2}, already on other Delivery Orders {3}").format(
					frappe.bold(item_code), frappe.bold(qty), ordered[item_code], allocated[item_code]
				)
			)
	if lines:
		frappe.throw(
			_("Delivery Order quantity is more than the pending quantity of Purchase Order {0}:").format(
				get_link_to_form("Purchase Order", po.name)
			)
			+ "<br><br>"
			+ "<br>".join(lines),
			title=_("Over Allocation"),
		)


@frappe.whitelist()
def make_delivery_order(purchase_order, items):
	"""Create (and save as draft) a Delivery Order from a submitted Purchase Order.

	items: JSON list of {"item_code", "qty"}. Returns the new Delivery Order name.
	"""
	if isinstance(items, str):
		items = json.loads(items)
	items = [d for d in items or [] if flt(d.get("qty")) > 0]
	if not items:
		frappe.throw(_("No valid quantities"))

	po = frappe.get_doc("Purchase Order", purchase_order)
	po.check_permission("read")
	frappe.has_permission(DELIVERY_ORDER, "create", throw=True)
	if po.docstatus != 1:
		frappe.throw(_("Submit the Purchase Order first."))

	order = frappe.new_doc(DELIVERY_ORDER)
	order.purchase_order = po.name
	order.supplier = po.supplier
	order.supplier_name = po.supplier_name
	order.transaction_date = po.transaction_date
	order.required_by = po.schedule_date or today()
	order.company = po.company

	net_total = total_qty = 0
	for d in items:
		po_item = next((i for i in po.items if i.item_code == d.get("item_code")), None)
		if not po_item:
			frappe.throw(_("Item not found in PO: {0}").format(d.get("item_code")))
		qty = flt(d.get("qty"))
		rate = flt(po_item.rate)
		amount = qty * rate
		order.append(
			"items",
			{
				"item_code": po_item.item_code,
				"item_name": po_item.item_name,
				"qty": qty,
				"uom": po_item.uom,
				"stock_uom": po_item.stock_uom,
				"schedule_date": po_item.schedule_date or today(),
				"conversion_factor": po_item.conversion_factor or 1,
				"rate": rate,
				"amount": amount,
				"base_rate": rate,
				"base_amount": amount,
				"warehouse": po_item.warehouse,
				"item_tax_template": po_item.item_tax_template,
			},
		)
		net_total += amount
		total_qty += qty

	order.total_quantity = total_qty
	order.total = net_total
	total_tax = add_gst_rows(order, po, net_total)
	order.total_taxes_and_charges = total_tax
	order.grand_total = net_total + total_tax

	order.insert(ignore_permissions=True)  # validate checks the Purchase Order pending quantity
	return order.name


def add_gst_rows(order, po, net_total):
	abbr = frappe.get_cached_value("Company", po.company, "abbr")
	company_state = str(frappe.get_cached_value("Company", po.company, "gst_state_number") or "").strip()
	supplier_gstin = frappe.db.get_value("Supplier", po.supplier, "gstin") or ""
	supplier_state = supplier_gstin[:2] if len(supplier_gstin) >= 2 else ""
	is_inter_state = bool(company_state and supplier_state and company_state != supplier_state)

	rates = {"cgst": 0, "sgst": 0, "igst": 0}
	for row in order.items:
		if not row.item_tax_template:
			continue
		for t in frappe.get_doc("Item Tax Template", row.item_tax_template).taxes:
			account = (t.tax_type or "").lower()
			for key in rates:
				if key in account:
					rates[key] = flt(t.tax_rate)
					break

	heads = ["igst"] if is_inter_state else ["cgst", "sgst"]
	running_total = net_total
	total_tax = 0
	for head in heads:
		amount = net_total * rates[head] / 100
		if amount <= 0:
			continue
		running_total += amount
		total_tax += amount
		order.append(
			"purchase_taxes_and_charges",
			{
				"charge_type": "On Net Total",
				"account_head": f"Input Tax {head.upper()} - {abbr}",
				"description": f"{head.upper()} @{rates[head]}%",
				"rate": rates[head],
				"tax_amount": amount,
				"total": running_total,
			},
		)
	return total_tax
