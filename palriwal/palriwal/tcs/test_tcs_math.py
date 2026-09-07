# Copyright (c) 2026, Reformiqo and contributors
# For license information, please see license.txt

"""Unit tests for the TCS arithmetic (FRD v3.0 Sheet 13 and TC-014 to TC-020, TC-034).

Runs with plain python - no frappe site needed:
    python -m unittest palriwal.palriwal.tcs.test_tcs_math
"""

import unittest

from palriwal.palriwal.tcs.tcs_math import (
	STATUS_BELOW,
	STATUS_CUMULATIVE,
	STATUS_NO_THRESHOLD,
	STATUS_SINGLE,
	compute_tcs,
)

# Sheet 13 category configuration
SHEET13 = dict(tax_rate=1, single_threshold=0, cumulative_threshold=5_000_000, collect_on_full_value=False)


class TestSheet13WorkedExample(unittest.TestCase):
	"""Reproduce column H of Sheet 13 exactly, invoice by invoice (TC-015, TC-016, TC-017)."""

	def test_invoice_1_below(self):
		r = compute_tcs(2_000_000, 0, **SHEET13)
		self.assertEqual(r["party_total"], 2_000_000)
		self.assertEqual(r["tcs_amount"], 0)
		self.assertEqual(r["status"], STATUS_BELOW)
		self.assertFalse(r["applies"])

	def test_invoice_2_below(self):
		r = compute_tcs(2_500_000, 2_000_000, **SHEET13)
		self.assertEqual(r["party_total"], 4_500_000)
		self.assertEqual(r["tcs_amount"], 0)
		self.assertEqual(r["status"], STATUS_BELOW)

	def test_invoice_3_crosses_excess_only(self):
		r = compute_tcs(1_800_000, 4_500_000, **SHEET13)
		self.assertEqual(r["party_total"], 6_300_000)
		self.assertEqual(r["taxable_portion"], 1_300_000)
		self.assertEqual(r["tcs_amount"], 13_000)
		self.assertEqual(r["status"], STATUS_CUMULATIVE)

	def test_invoice_4_capped_at_invoice_base(self):
		r = compute_tcs(1_000_000, 6_300_000, **SHEET13)
		self.assertEqual(r["party_total"], 7_300_000)
		self.assertEqual(r["taxable_portion"], 1_000_000)  # excess is 2,300,000 - capped (BR-022)
		self.assertEqual(r["tcs_amount"], 10_000)
		self.assertEqual(r["status"], STATUS_CUMULATIVE)

	def test_total_matches_sheet(self):
		amounts = [
			compute_tcs(2_000_000, 0, **SHEET13)["tcs_amount"],
			compute_tcs(2_500_000, 2_000_000, **SHEET13)["tcs_amount"],
			compute_tcs(1_800_000, 4_500_000, **SHEET13)["tcs_amount"],
			compute_tcs(1_000_000, 6_300_000, **SHEET13)["tcs_amount"],
		]
		self.assertEqual(sum(amounts), 23_000)

	def test_collect_on_full_value_invoice_3(self):
		# Sheet 13 reading note 4 / TC-018: invoice 3 attracts TCS on its entire base
		r = compute_tcs(1_800_000, 4_500_000, **{**SHEET13, "collect_on_full_value": True})
		self.assertEqual(r["taxable_portion"], 1_800_000)
		self.assertEqual(r["tcs_amount"], 18_000)


class TestThresholdVariants(unittest.TestCase):
	def test_single_threshold_crossed(self):
		# TC-014
		r = compute_tcs(150_000, 0, tax_rate=1, single_threshold=100_000, cumulative_threshold=0)
		self.assertEqual(r["status"], STATUS_SINGLE)
		self.assertEqual(r["tcs_amount"], 1_500)

	def test_single_threshold_not_crossed_exact_value(self):
		r = compute_tcs(100_000, 0, tax_rate=1, single_threshold=100_000, cumulative_threshold=0)
		self.assertEqual(r["status"], STATUS_BELOW)
		self.assertEqual(r["tcs_amount"], 0)

	def test_single_crossed_takes_precedence_over_cumulative(self):
		# Step 7 is tested before step 8; a single crossing charges the whole invoice.
		r = compute_tcs(150_000, 0, tax_rate=1, single_threshold=100_000, cumulative_threshold=5_000_000)
		self.assertEqual(r["status"], STATUS_SINGLE)
		self.assertEqual(r["taxable_portion"], 150_000)

	def test_below_both(self):
		# TC-019
		r = compute_tcs(50_000, 0, tax_rate=1, single_threshold=100_000, cumulative_threshold=500_000)
		self.assertEqual(r["status"], STATUS_BELOW)
		self.assertFalse(r["applies"])
		self.assertEqual(r["tcs_amount"], 0)

	def test_no_threshold_configured(self):
		# TC-020
		r = compute_tcs(118_000, 0, tax_rate=1)
		self.assertEqual(r["status"], STATUS_NO_THRESHOLD)
		self.assertEqual(r["taxable_portion"], 118_000)
		self.assertEqual(r["tcs_amount"], 1_180)  # Sheet 11 illustration

	def test_precision_rounding(self):
		r = compute_tcs(123_456.78, 0, tax_rate=1)
		self.assertEqual(r["tcs_amount"], 1_234.57)

	def test_round_off_tax_amount(self):
		# FR-009 / BR-023
		r = compute_tcs(123_456.78, 0, tax_rate=1, round_off_tax_amount=True)
		self.assertEqual(r["tcs_amount"], 1_235)

	def test_zero_result_does_not_apply(self):
		# TC-025 - a calculation that yields zero leaves no row
		r = compute_tcs(0, 0, tax_rate=1)
		self.assertFalse(r["applies"])

	def test_idempotent_on_repeated_save(self):
		# TC-023 - same inputs, same output, no creep
		first = compute_tcs(1_800_000, 4_500_000, **SHEET13)
		for _ in range(5):
			self.assertEqual(compute_tcs(1_800_000, 4_500_000, **SHEET13), first)


class TestPurchaseReturns(unittest.TestCase):
	"""BR-030 / TC-034: returns recalculate on a negative base and reduce the party total."""

	def test_return_reverses_excess_only(self):
		# After Sheet 13 invoice 3 (party total 6.3M) a 500,000 return is raised.
		r = compute_tcs(-500_000, 6_300_000, **SHEET13)
		self.assertEqual(r["party_total"], 5_800_000)
		self.assertEqual(r["taxable_portion"], -500_000)
		self.assertEqual(r["tcs_amount"], -5_000)
		self.assertEqual(r["status"], STATUS_CUMULATIVE)

	def test_return_capped_at_amount_above_threshold(self):
		# Only 1.3M of the 6.3M ever attracted TCS, so a 2M return reverses TCS on 1.3M.
		r = compute_tcs(-2_000_000, 6_300_000, **SHEET13)
		self.assertEqual(r["taxable_portion"], -1_300_000)
		self.assertEqual(r["tcs_amount"], -13_000)

	def test_return_below_threshold_has_no_tcs(self):
		r = compute_tcs(-500_000, 4_500_000, **SHEET13)
		self.assertEqual(r["tcs_amount"], 0)
		self.assertEqual(r["status"], STATUS_BELOW)

	def test_return_no_threshold(self):
		r = compute_tcs(-118_000, 0, tax_rate=1)
		self.assertEqual(r["tcs_amount"], -1_180)
		self.assertTrue(r["applies"])


if __name__ == "__main__":
	unittest.main()
