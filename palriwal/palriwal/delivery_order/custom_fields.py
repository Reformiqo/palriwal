# Copyright (c) 2026, Reformiqo and contributors
# For license information, please see license.txt

"""Custom fields for the Delivery Order -> Delivery Note -> Purchase Receipt flow.

Delivery Order is a site-level custom DocType whose ``items`` table reuses the standard
Purchase Order Item child table, so the per-row Delivered / Pending Qty live on Purchase Order
Item and only show when the row belongs to a Delivery Order. Delivery Note Item and Purchase
Receipt Item get the row-level links that make the quantities exact.

Created idempotently from ``after_install`` / ``after_migrate`` and from the setup patch.
Skipped on a site without the Delivery Order DocType.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from palriwal.palriwal.delivery_order.qty_math import (
	STATUS_FULLY_DELIVERED,
	STATUS_NOT_DELIVERED,
	STATUS_PARTLY_DELIVERED,
)

MODULE = "Palriwal"
DELIVERY_ORDER = "Delivery Order"
ON_DELIVERY_ORDER = "eval:doc.parenttype=='Delivery Order'"


def get_custom_fields():
	return {
		# Delivery Order Item table (= Purchase Order Item rows with parenttype Delivery Order)
		"Purchase Order Item": [
			{
				"fieldname": "custom_delivered_qty",
				"label": "Delivered Qty",
				"fieldtype": "Float",
				"insert_after": "qty",
				"read_only": 1,
				"allow_on_submit": 1,
				"no_copy": 1,
				"print_hide": 1,
				"depends_on": ON_DELIVERY_ORDER,
				"description": "Delivery Order only: total quantity of submitted Delivery Notes against this row.",
				"module": MODULE,
			},
			{
				"fieldname": "custom_pending_qty",
				"label": "Pending Qty",
				"fieldtype": "Float",
				"insert_after": "custom_delivered_qty",
				"read_only": 1,
				"allow_on_submit": 1,
				"no_copy": 1,
				"print_hide": 1,
				"depends_on": ON_DELIVERY_ORDER,
				"description": "Delivery Order only: Quantity - Delivered Qty.",
				"module": MODULE,
			},
		],
		DELIVERY_ORDER: [
			{
				"fieldname": "custom_delivery_status_section",
				"label": "Delivery Status",
				"fieldtype": "Section Break",
				"insert_after": "grand_total",
				"module": MODULE,
			},
			{
				"fieldname": "custom_delivery_status",
				"label": "Delivery Status",
				"fieldtype": "Select",
				"options": "\n".join([STATUS_NOT_DELIVERED, STATUS_PARTLY_DELIVERED, STATUS_FULLY_DELIVERED]),
				"default": STATUS_NOT_DELIVERED,
				"insert_after": "custom_delivery_status_section",
				"read_only": 1,
				"allow_on_submit": 1,
				"no_copy": 1,
				"in_list_view": 1,
				"in_standard_filter": 1,
				"module": MODULE,
			},
			{
				"fieldname": "custom_delivery_status_cb",
				"fieldtype": "Column Break",
				"insert_after": "custom_delivery_status",
				"module": MODULE,
			},
			{
				"fieldname": "custom_total_delivered_qty",
				"label": "Total Delivered Qty",
				"fieldtype": "Float",
				"insert_after": "custom_delivery_status_cb",
				"read_only": 1,
				"allow_on_submit": 1,
				"no_copy": 1,
				"module": MODULE,
			},
			{
				"fieldname": "custom_total_pending_qty",
				"label": "Total Pending Qty",
				"fieldtype": "Float",
				"insert_after": "custom_total_delivered_qty",
				"read_only": 1,
				"allow_on_submit": 1,
				"no_copy": 1,
				"module": MODULE,
			},
		],
		# Row-level link to the Delivery Order row. Copied on returns, so a return reduces the
		# delivered quantity of the same row.
		"Delivery Note Item": [
			{
				"fieldname": "custom_delivery_order",
				"label": "Delivery Order",
				"fieldtype": "Link",
				"options": DELIVERY_ORDER,
				"insert_after": "dn_detail",
				"read_only": 1,
				"print_hide": 1,
				"search_index": 1,
				"module": MODULE,
			},
			{
				"fieldname": "custom_delivery_order_item",
				"label": "Delivery Order Item",
				"fieldtype": "Data",
				"insert_after": "custom_delivery_order",
				"read_only": 1,
				"print_hide": 1,
				"search_index": 1,
				"module": MODULE,
			},
		],
		"Purchase Receipt Item": [
			{
				"fieldname": "custom_delivery_note_item",
				"label": "Delivery Note Item",
				"fieldtype": "Data",
				"insert_after": "purchase_order_item",
				"read_only": 1,
				"print_hide": 1,
				"module": MODULE,
			},
		],
	}


def setup_custom_fields():
	"""Create (or update) the Delivery Order flow custom fields. Safe to run repeatedly."""
	if not frappe.db.exists("DocType", DELIVERY_ORDER):
		return
	create_custom_fields(get_custom_fields(), ignore_validate=frappe.flags.in_patch, update=True)
	frappe.clear_cache(doctype=DELIVERY_ORDER)
