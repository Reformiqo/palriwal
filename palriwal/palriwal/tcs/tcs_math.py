# Copyright (c) 2026, Reformiqo and contributors
# For license information, please see license.txt

"""Pure arithmetic of the TCS engine (FRD v3.0, Sheet 10 steps 7 to 12).

This module deliberately has NO frappe dependency so the threshold logic can be
unit-tested against Sheet 13 of the FRD with plain python. All the database work
(loading the category, resolving the rate and account, summing the party total)
lives in ``engine.py``; only the numbers come through here.
"""

# Threshold Status values (Sheet 9, field 7). Display only - never drives logic (BR-029).
STATUS_BELOW = "Below Single and Cumulative"
STATUS_SINGLE = "Single Threshold Crossed"
STATUS_CUMULATIVE = "Cumulative Threshold Crossed"
STATUS_NO_THRESHOLD = "No Threshold Configured"
# FR-030: a foreign currency invoice shows the reason and applies no TCS.
STATUS_FOREIGN_CURRENCY = "Not Applied - Foreign Currency"

THRESHOLD_STATUSES = (STATUS_BELOW, STATUS_SINGLE, STATUS_CUMULATIVE, STATUS_NO_THRESHOLD)


def _round(value, precision):
	"""Round half away from zero, the way ERPNext's flt() rounds currency."""
	q = 10**precision
	sign = -1 if value < 0 else 1
	return sign * (int(abs(value) * q + 0.5 + 1e-9)) / q


def compute_tcs(
	invoice_base,
	prior_party_total,
	tax_rate,
	single_threshold=0,
	cumulative_threshold=0,
	collect_on_full_value=False,
	round_off_tax_amount=False,
	precision=2,
):
	"""Run steps 7 to 12 of the calculation algorithm.

	:param invoice_base: base of the CURRENT invoice (Grand Total or Net Total per the
	        category) with the engine's own row removed. Negative for a purchase return.
	:param prior_party_total: sum of the same base across the OTHER submitted invoices for
	        this supplier, category and financial year (BR-021). Returns already carry a
	        negative base, so they reduce this figure naturally (BR-030).
	:param tax_rate: percentage, 1 means 1%.
	:param single_threshold: 0 means no single transaction threshold.
	:param cumulative_threshold: 0 means no cumulative threshold.
	:param collect_on_full_value: ticked = whole base once crossed, unticked = excess only.
	:param round_off_tax_amount: ticked = round to whole units (BR-023).
	:param precision: company currency precision.
	:returns: dict(applies, status, party_total, taxable_portion, tcs_amount)
	"""
	invoice_base = float(invoice_base or 0)
	prior_party_total = float(prior_party_total or 0)
	single_threshold = float(single_threshold or 0)
	cumulative_threshold = float(cumulative_threshold or 0)
	tax_rate = float(tax_rate or 0)

	is_return = invoice_base < 0
	magnitude = abs(invoice_base)
	party_total = prior_party_total + invoice_base

	# For a normal invoice the cumulative position is tested AFTER adding this invoice.
	# For a return the question is whether TCS had been collected on what is being
	# returned, so the position BEFORE the return is the reference (BR-030).
	reference_total = prior_party_total if is_return else party_total

	single_crossed = single_threshold > 0 and magnitude > single_threshold
	cumulative_crossed = cumulative_threshold > 0 and reference_total > cumulative_threshold
	no_threshold = not single_threshold and not cumulative_threshold

	# Steps 7, 8, 9 in that order.
	if single_crossed:
		status = STATUS_SINGLE
	elif cumulative_crossed:
		status = STATUS_CUMULATIVE
	elif no_threshold:
		status = STATUS_NO_THRESHOLD
	else:
		# Step 10: neither crossed.
		return {
			"applies": False,
			"status": STATUS_BELOW,
			"party_total": party_total,
			"taxable_portion": 0.0,
			"tcs_amount": 0.0,
		}

	# Step 11: taxable portion.
	if collect_on_full_value or single_crossed or no_threshold:
		# Whole current invoice base. The single transaction threshold is a per-invoice
		# test, so once a single invoice crosses it the whole invoice is chargeable;
		# with no thresholds every invoice is chargeable in full.
		taxable = magnitude
	else:
		# Excess over the cumulative threshold, capped at the current invoice base (BR-022).
		excess = reference_total - cumulative_threshold
		taxable = min(excess, magnitude)

	taxable = max(taxable, 0.0)
	if is_return:
		taxable = -taxable

	# Step 12: apply the rate and round (BR-023).
	amount = taxable * tax_rate / 100.0
	amount = _round(amount, 0 if round_off_tax_amount else precision)
	taxable = _round(taxable, precision)

	return {
		"applies": bool(amount),
		"status": status,
		"party_total": party_total,
		"taxable_portion": taxable,
		"tcs_amount": amount,
	}
