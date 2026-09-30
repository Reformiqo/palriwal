# Copyright (c) 2026, Reformiqo and contributors
# For license information, please see license.txt

"""Quantity arithmetic for the Delivery Order -> Delivery Note -> Purchase Receipt flow.

No frappe dependency, so the rules can be unit tested with plain python:
    python -m unittest palriwal.palriwal.delivery_order.test_qty_math

A Delivery Order row is identified by its row name. "Delivered" is the cumulative Delivery
Note quantity against the row (returns count negative), "Pending" is row qty - delivered.
"""

STATUS_NOT_DELIVERED = "Not Delivered"
STATUS_PARTLY_DELIVERED = "Partly Delivered"
STATUS_FULLY_DELIVERED = "Fully Delivered"

DEFAULT_PRECISION = 3


def rounded(value, precision=DEFAULT_PRECISION):
	return round(float(value or 0), precision) + 0.0  # + 0.0 turns -0.0 into 0.0


def pending_qty(ordered, delivered, precision=DEFAULT_PRECISION):
	return rounded(rounded(ordered, precision) - rounded(delivered, precision), precision)


def row_status(ordered, delivered, precision=DEFAULT_PRECISION):
	delivered = rounded(delivered, precision)
	if delivered <= 0:
		return STATUS_NOT_DELIVERED
	if pending_qty(ordered, delivered, precision) <= 0:
		return STATUS_FULLY_DELIVERED
	return STATUS_PARTLY_DELIVERED


def summarise(rows, delivered, precision=DEFAULT_PRECISION):
	"""Totals and status of a whole Delivery Order.

	rows: [{"name", "qty"}]; delivered: {row name: delivered qty}.
	Fully Delivered only when every row is; Not Delivered only when nothing is.
	"""
	total_qty = rounded(sum(float(r["qty"] or 0) for r in rows), precision)
	total_delivered = rounded(sum(delivered.get(r["name"], 0) for r in rows), precision)
	statuses = {row_status(r["qty"], delivered.get(r["name"], 0), precision) for r in rows}

	if not rows or statuses == {STATUS_NOT_DELIVERED}:
		status = STATUS_NOT_DELIVERED
	elif statuses == {STATUS_FULLY_DELIVERED}:
		status = STATUS_FULLY_DELIVERED
	else:
		status = STATUS_PARTLY_DELIVERED

	return {
		"total_qty": total_qty,
		"delivered_qty": total_delivered,
		"pending_qty": pending_qty(total_qty, total_delivered, precision),
		"status": status,
	}


def allocate(note_rows, order_rows, already_delivered, precision=DEFAULT_PRECISION):
	"""Decide which Delivery Order row each Delivery Note row delivers against.

	note_rows: [{"key", "item_code", "qty", "linked"}] - "linked" is the row the note already
	points at (kept when it is a row of this order), else None.
	order_rows: [{"name", "item_code", "qty"}] in display order.
	already_delivered: {order row name: qty delivered by other submitted notes}.

	An unlinked note row goes to the first order row of the same item that still has pending
	quantity, else the first order row of that item (the over-delivery check then reports it),
	else None (item not on the order - left out of the flow).
	Returns {note row key: order row name or None}.
	"""
	valid = {r["name"] for r in order_rows}
	remaining = {
		r["name"]: pending_qty(r["qty"], already_delivered.get(r["name"], 0), precision) for r in order_rows
	}

	result = {}
	for row in note_rows:
		if row.get("linked") in valid:
			result[row["key"]] = row["linked"]
			remaining[row["linked"]] -= float(row["qty"] or 0)

	for row in note_rows:
		if row["key"] in result:
			continue
		candidates = [r["name"] for r in order_rows if r["item_code"] == row["item_code"]]
		target = next((c for c in candidates if rounded(remaining[c], precision) > 0), None)
		if not target and candidates:
			target = candidates[0]
		result[row["key"]] = target
		if target:
			remaining[target] -= float(row["qty"] or 0)

	return result


def over_deliveries(requested, order_rows, already_delivered, precision=DEFAULT_PRECISION):
	"""Order rows this note would over-deliver.

	requested: {order row name: qty on this note}. Returns a list of dicts with
	row, ordered, delivered, pending and requested for every row where requested > pending.
	"""
	problems = []
	for row in order_rows:
		qty = rounded(requested.get(row["name"], 0), precision)
		if qty <= 0:
			continue
		delivered = rounded(already_delivered.get(row["name"], 0), precision)
		pending = pending_qty(row["qty"], delivered, precision)
		if rounded(qty - pending, precision) > 0:
			problems.append(
				{
					"row": row,
					"ordered": rounded(row["qty"], precision),
					"delivered": delivered,
					"pending": max(pending, 0.0),
					"requested": qty,
				}
			)
	return problems
