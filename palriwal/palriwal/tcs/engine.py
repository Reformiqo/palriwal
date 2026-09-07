# Copyright (c) 2026, Reformiqo and contributors
# For license information, please see license.txt

"""Purchase Invoice TCS calculation engine (FRD v3.0, Sheet 10).

A direct mirror of the way the native TDS engine works on a Purchase Invoice:

* runs on ``validate`` (hooks.py -> doc_events),
* owns exactly ONE row in Purchase Taxes and Charges, flagged ``custom_is_tcs_row``,
  charge_type Actual, add_deduct_tax Add (TCS collected by the supplier INCREASES what
  we owe - it is debited to a TCS Receivable asset account),
* writes five read-only tracking fields on the invoice,
* never posts GL itself - the standard invoice posting logic does that.

The arithmetic (steps 7 to 12) lives in ``tcs_math.py`` so it can be unit-tested
without a site; everything here is database work and document plumbing.
"""

import erpnext
import frappe
from erpnext.accounts.utils import get_fiscal_year
from frappe import _
from frappe.query_builder.functions import IfNull, Sum
from frappe.utils import cint, flt, getdate

from palriwal.palriwal.tcs.tcs_math import STATUS_FOREIGN_CURRENCY, compute_tcs

TRACKING_FIELDS = (
	"custom_tcs_section",
	"custom_tcs_rate",
	"custom_tcs_base_amount",
	"custom_tcs_amount",
	"custom_tcs_threshold_status",
)


# ----------------------------------------------------------------------
# hooks.py entry points
# ----------------------------------------------------------------------
def validate(doc, method=None):
	"""Purchase Invoice ``validate`` - trigger point 1 (Sheet 10)."""
	TCSEngine(doc).run()


def before_submit(doc, method=None):
	"""BR-027: warn (do not block) when TCS was applied and the supplier has no PAN."""
	if not (cint(doc.get("custom_apply_tcs")) and flt(doc.get("custom_tcs_amount"))):
		return

	pan = get_supplier_pan(doc.supplier)
	if not pan:
		frappe.msgprint(
			_(
				"TCS of {0} has been applied on this invoice but supplier {1} has no PAN on record. "
				"The PAN is needed to reconcile the TCS credit with Form 26AS."
			).format(
				frappe.bold(frappe.format_value(doc.custom_tcs_amount, {"fieldtype": "Currency"})),
				frappe.bold(doc.supplier),
			),
			title=_("Supplier PAN missing"),
			indicator="orange",
		)


@frappe.whitelist()
def get_tcs_details(doc):
	"""Run the engine on an unsaved invoice for the client-side triggers (Sheet 10, rows 3-5).

	Returns the tracking field values and the engine tax row (or None) so the form can
	show the effect immediately. The server-side ``validate`` remains the authority on save.
	"""
	doc = frappe.get_doc(frappe.parse_json(doc))
	engine = TCSEngine(doc)
	engine.run()

	tax_row = engine.get_engine_row()
	return {
		"fields": {f: doc.get(f) for f in TRACKING_FIELDS},
		"custom_tcs_category": doc.get("custom_tcs_category"),
		"tax_row": tax_row.as_dict(no_default_fields=True, no_child_table_fields=True) if tax_row else None,
	}


@frappe.whitelist()
def get_supplier_tcs_category(supplier):
	"""BR-014: the category to default on the invoice, blank when the supplier has none
	or the configured category is no longer active."""
	if not supplier:
		return None
	category = frappe.get_cached_value("Supplier", supplier, "custom_tcs_category")
	if category and cint(frappe.get_cached_value("TCS Category", category, "is_active")):
		return category
	return None


def get_supplier_pan(supplier):
	meta = frappe.get_meta("Supplier")
	fieldname = "pan" if meta.has_field("pan") else "tax_id"
	return frappe.db.get_value("Supplier", supplier, fieldname)


# ----------------------------------------------------------------------
# Engine
# ----------------------------------------------------------------------
class TCSEngine:
	def __init__(self, doc):
		self.doc = doc

	# -- orchestration -------------------------------------------------
	def run(self):
		# Step 5 prerequisite / BR-015: the engine's own row is stripped BEFORE anything
		# is measured, so the base can never include last save's TCS.
		self.remove_engine_row()

		# Step 1: guard
		if not self.is_applicable():
			self.clear_tracking_fields()
			self.finish()
			return

		# BR-028 / FR-030: company currency only in phase 1
		if not self.is_company_currency():
			self.clear_tracking_fields(status=STATUS_FOREIGN_CURRENCY)
			frappe.msgprint(
				_("TCS is applied only to invoices in the company currency. No TCS has been applied."),
				indicator="orange",
				alert=True,
			)
			self.finish()
			return

		# Step 2: load the category (throws if inactive / expired - BR-010, BR-013)
		category = self.get_category()

		# Step 3: resolve the account (BR-011)
		account_head = category.get_company_account(self.doc.company)

		# Step 4: resolve the rate (BR-012)
		rate_row = category.get_applicable_rate_row(self.doc.posting_date)

		# Step 5: the invoice base, engine row already removed
		invoice_base = self.get_invoice_base(category.calculation_base)

		# Step 6: the party total across submitted invoices in the financial year (BR-021)
		prior_party_total = self.get_prior_party_total(category)

		# Steps 7 to 12
		result = compute_tcs(
			invoice_base=invoice_base,
			prior_party_total=prior_party_total,
			tax_rate=rate_row.tax_rate,
			single_threshold=rate_row.single_threshold,
			cumulative_threshold=rate_row.cumulative_threshold,
			collect_on_full_value=cint(category.collect_on_full_value),
			round_off_tax_amount=cint(category.round_off_tax_amount),
			precision=self.doc.precision("base_grand_total") or 2,
		)

		# Step 13: tracking fields (BR-029: status is informational)
		self.doc.custom_tcs_section = category.statutory_section
		self.doc.custom_tcs_rate = flt(rate_row.tax_rate)
		self.doc.custom_tcs_base_amount = result["taxable_portion"]
		self.doc.custom_tcs_amount = result["tcs_amount"]
		self.doc.custom_tcs_threshold_status = result["status"]

		# Step 14: the engine row - only when there is an amount (BR-024)
		if result["tcs_amount"]:
			self.insert_engine_row(
				account_head=account_head,
				section=category.statutory_section,
				rate=rate_row.tax_rate,
				amount=result["tcs_amount"],
			)

		# Step 15: standard totals
		self.finish()

	# -- guards ----------------------------------------------------------
	def is_applicable(self):
		if self.doc.get("is_opening") == "Yes":
			return False

		if not cint(self.doc.get("custom_apply_tcs")):
			return False

		# BR-014 server-side fallback for API / mapped documents: default from the supplier.
		if not self.doc.get("custom_tcs_category") and self.doc.get("supplier"):
			self.doc.custom_tcs_category = get_supplier_tcs_category(self.doc.supplier)

		return bool(self.doc.get("custom_tcs_category"))

	def is_company_currency(self):
		company_currency = erpnext.get_company_currency(self.doc.company)
		return not self.doc.get("currency") or self.doc.currency == company_currency

	def get_category(self):
		category = frappe.get_cached_doc("TCS Category", self.doc.custom_tcs_category)
		category.validate_usable_on(self.doc.posting_date)
		return category

	# -- measurement -----------------------------------------------------
	def get_invoice_base(self, calculation_base):
		"""Grand Total or Net Total in company currency, engine row excluded (FR-016)."""
		self.doc.calculate_taxes_and_totals()
		if calculation_base == "Net Total":
			return flt(self.doc.base_net_total)
		return flt(self.doc.base_grand_total)

	def get_prior_party_total(self, category):
		"""Sum of the same base over the OTHER submitted Purchase Invoices of this supplier
		in the financial year (BR-021). Drafts and cancelled invoices are excluded, returns
		carry a negative base and reduce the total (BR-030).

		With Consider Entire Party Ledger Amount ticked, every submitted invoice of the
		supplier counts regardless of category or the Apply TCS flag.
		"""
		fiscal_year = get_fiscal_year(self.doc.posting_date, company=self.doc.company)
		year_start, year_end = getdate(fiscal_year[1]), getdate(fiscal_year[2])

		pi = frappe.qb.DocType("Purchase Invoice")
		if category.calculation_base == "Net Total":
			base = Sum(pi.base_net_total)
		else:
			# a submitted invoice's grand total already carries its own TCS row - take it out
			base = Sum(pi.base_grand_total - IfNull(pi.custom_tcs_amount, 0))

		query = (
			frappe.qb.from_(pi)
			.select(base)
			.where(pi.docstatus == 1)
			.where(pi.company == self.doc.company)
			.where(pi.supplier == self.doc.supplier)
			.where(pi.posting_date >= year_start)
			.where(pi.posting_date <= year_end)
			.where(IfNull(pi.is_opening, "No") != "Yes")
		)
		if self.doc.name:
			query = query.where(pi.name != self.doc.name)

		if not cint(category.consider_party_ledger_amount):
			query = query.where(pi.custom_apply_tcs == 1).where(pi.custom_tcs_category == category.name)

		result = query.run()
		return flt(result[0][0]) if result else 0.0

	# -- the engine row (BR-016 to BR-018, BR-024) -----------------------
	def get_engine_row(self):
		for row in self.doc.get("taxes") or []:
			if cint(row.get("custom_is_tcs_row")):
				return row
		return None

	def remove_engine_row(self):
		taxes = self.doc.get("taxes") or []
		kept = [row for row in taxes if not cint(row.get("custom_is_tcs_row"))]
		if len(kept) != len(taxes):
			self.doc.set("taxes", kept)
			for idx, row in enumerate(self.doc.taxes, start=1):
				row.idx = idx

	def insert_engine_row(self, account_head, section, rate, amount):
		# Appended after remove_engine_row(), so it is always the last row (BR-018) and no
		# other row is ever touched (BR-016).
		self.doc.append(
			"taxes",
			{
				"custom_is_tcs_row": 1,
				"category": "Total",
				"charge_type": "Actual",
				"add_deduct_tax": "Add",
				"account_head": account_head,
				"description": _("TCS {0} @ {1}%").format(section, f"{flt(rate):g}"),
				"cost_center": self.doc.get("cost_center")
				or erpnext.get_default_cost_center(self.doc.company),
				"rate": 0,
				"tax_amount": amount,
				"base_tax_amount": amount,
			},
		)

	# -- bookkeeping -----------------------------------------------------
	def clear_tracking_fields(self, status=None):
		"""BR-025 / FR-027: no orphan values."""
		self.doc.custom_tcs_section = None
		self.doc.custom_tcs_rate = 0
		self.doc.custom_tcs_base_amount = 0
		self.doc.custom_tcs_amount = 0
		self.doc.custom_tcs_threshold_status = status

	def finish(self):
		"""Step 15: let the standard Purchase Invoice calculation pick up the taxes table."""
		self.doc.calculate_taxes_and_totals()

		# The standard validate already built the payment schedule against the pre-TCS
		# grand total; rescale it with the same standard method so the schedule and the
		# invoice agree at submit.
		if (
			self.doc.get("payment_schedule")
			and not self.doc.get("is_return")
			and self.doc.get("is_opening") != "Yes"
			and hasattr(self.doc, "set_payment_schedule")
		):
			self.doc.set_payment_schedule()
