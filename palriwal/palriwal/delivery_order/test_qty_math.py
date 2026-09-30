# Copyright (c) 2026, Reformiqo and contributors
# For license information, please see license.txt

"""Unit tests for the Delivery Order quantity rules.

Runs with plain python - no frappe site needed:
    python -m unittest palriwal.palriwal.delivery_order.test_qty_math
"""

import unittest

from palriwal.palriwal.delivery_order.qty_math import (
	STATUS_FULLY_DELIVERED,
	STATUS_NOT_DELIVERED,
	STATUS_PARTLY_DELIVERED,
	allocate,
	over_deliveries,
	pending_qty,
	summarise,
)

ORDER = [{"name": "r1", "item_code": "Non Coking Coal", "qty": 200}]


class TestRequirementScenarios(unittest.TestCase):
	"""Delivery Order of 200 delivered as 55 + 100 + 45."""

	def test_scenario_1(self):
		s = summarise(ORDER, {"r1": 55})
		self.assertEqual(
			(s["delivered_qty"], s["pending_qty"], s["status"]), (55, 145, STATUS_PARTLY_DELIVERED)
		)

	def test_scenario_2(self):
		s = summarise(ORDER, {"r1": 155})
		self.assertEqual(
			(s["delivered_qty"], s["pending_qty"], s["status"]), (155, 45, STATUS_PARTLY_DELIVERED)
		)

	def test_scenario_3(self):
		s = summarise(ORDER, {"r1": 200})
		self.assertEqual(
			(s["delivered_qty"], s["pending_qty"], s["status"]), (200, 0, STATUS_FULLY_DELIVERED)
		)

	def test_nothing_delivered(self):
		s = summarise(ORDER, {})
		self.assertEqual((s["delivered_qty"], s["pending_qty"], s["status"]), (0, 200, STATUS_NOT_DELIVERED))

	def test_cancel_of_second_note_restores_pending(self):
		# 55 + 100 submitted, then the 100 is cancelled: back to scenario 1
		s = summarise(ORDER, {"r1": 55})
		self.assertEqual(s["pending_qty"], 145)

	def test_return_reduces_delivered(self):
		s = summarise(ORDER, {"r1": 200 - 20})
		self.assertEqual((s["pending_qty"], s["status"]), (20, STATUS_PARTLY_DELIVERED))


class TestOverDelivery(unittest.TestCase):
	def test_within_pending_is_allowed(self):
		self.assertEqual(over_deliveries({"r1": 145}, ORDER, {"r1": 55}), [])

	def test_one_more_than_pending_is_blocked(self):
		problems = over_deliveries({"r1": 46}, ORDER, {"r1": 155})
		self.assertEqual(len(problems), 1)
		self.assertEqual((problems[0]["pending"], problems[0]["requested"]), (45, 46))

	def test_fully_delivered_blocks_any_qty(self):
		problems = over_deliveries({"r1": 0.01}, ORDER, {"r1": 200})
		self.assertEqual(problems[0]["pending"], 0)

	def test_float_noise_is_not_over_delivery(self):
		self.assertEqual(over_deliveries({"r1": 33.84 + 21.49 + 144.67}, ORDER, {}), [])
		self.assertEqual(pending_qty(200, 33.84 + 21.49 + 144.67), 0)


TWO_ROWS = [
	{"name": "a", "item_code": "Coal", "qty": 100},
	{"name": "b", "item_code": "Coal", "qty": 100},
	{"name": "c", "item_code": "Sand", "qty": 10},
]


class TestAllocate(unittest.TestCase):
	def test_existing_valid_link_is_kept(self):
		res = allocate([{"key": 1, "item_code": "Coal", "qty": 5, "linked": "b"}], TWO_ROWS, {})
		self.assertEqual(res, {1: "b"})

	def test_unlinked_row_goes_to_first_row_with_pending(self):
		res = allocate([{"key": 1, "item_code": "Coal", "qty": 5, "linked": None}], TWO_ROWS, {"a": 100})
		self.assertEqual(res, {1: "b"})

	def test_stale_link_is_replaced(self):
		res = allocate([{"key": 1, "item_code": "Sand", "qty": 5, "linked": "other-order-row"}], TWO_ROWS, {})
		self.assertEqual(res, {1: "c"})

	def test_item_not_on_order_is_left_out(self):
		res = allocate([{"key": 1, "item_code": "Freight", "qty": 1, "linked": None}], TWO_ROWS, {})
		self.assertEqual(res, {1: None})

	def test_everything_delivered_still_links_for_the_over_delivery_message(self):
		res = allocate(
			[{"key": 1, "item_code": "Coal", "qty": 5, "linked": None}], TWO_ROWS, {"a": 100, "b": 100}
		)
		self.assertEqual(res, {1: "a"})


if __name__ == "__main__":
	unittest.main()
