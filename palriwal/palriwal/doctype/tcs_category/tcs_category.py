# Copyright (c) 2026, Reformiqo and contributors
# For license information, please see license.txt

"""TCS Category master - the TCS equivalent of Tax Withholding Category.

Structured after erpnext/accounts/doctype/tax_withholding_category. Business rules
BR-001 to BR-008 of FRD v3.0 (Sheet 12) are enforced in ``validate``; the two
resolvers used by the Purchase Invoice engine live here as well so the master owns
its own lookup logic, exactly as the standard master does.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, formatdate, getdate


class TCSCategory(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from palriwal.palriwal.doctype.tcs_account.tcs_account import TCSAccount
		from palriwal.palriwal.doctype.tcs_rate.tcs_rate import TCSRate

		accounts: DF.Table[TCSAccount]
		calculation_base: DF.Literal["Grand Total", "Net Total"]
		category_name: DF.Data
		collect_on_full_value: DF.Check
		consider_party_ledger_amount: DF.Check
		effective_from: DF.Date | None
		effective_to: DF.Date | None
		form_27eq_code: DF.Data | None
		is_active: DF.Check
		nature_of_collection: DF.Data | None
		rates: DF.Table[TCSRate]
		round_off_tax_amount: DF.Check
		statutory_section: DF.Data
	# end: auto-generated types

	def validate(self):
		self.validate_effective_window()  # BR-005
		self.validate_rates()  # BR-001, BR-002, BR-007, BR-008
		self.validate_accounts()  # BR-003, BR-004

	# ------------------------------------------------------------------
	# Master validations
	# ------------------------------------------------------------------
	def validate_effective_window(self):
		if self.effective_from and self.effective_to:
			if getdate(self.effective_to) < getdate(self.effective_from):
				frappe.throw(_("Effective To cannot be earlier than Effective From"))

	def validate_rates(self):
		for d in self.get("rates"):
			# BR-002: both dates are reqd on the child, this covers API inserts too
			if not d.from_date or not d.to_date:
				frappe.throw(_("Row #{0}: From Date and To Date are both mandatory").format(d.idx))
			if getdate(d.from_date) > getdate(d.to_date):
				frappe.throw(_("Row #{0}: From Date cannot be after To Date").format(d.idx))

			# BR-007
			if flt(d.tax_rate) <= 0 or flt(d.tax_rate) > 100:
				frappe.throw(_("Row #{0}: Rate must be between 0 and 100").format(d.idx))

			# BR-008
			if flt(d.single_threshold) < 0 or flt(d.cumulative_threshold) < 0:
				frappe.throw(_("Row #{0}: Thresholds cannot be negative").format(d.idx))

		# BR-001: no overlapping periods
		rates = sorted(self.get("rates"), key=lambda d: getdate(d.from_date))
		previous = None
		for d in rates:
			if previous and getdate(d.from_date) <= getdate(previous.to_date):
				frappe.throw(_("Row #{0}: Rate period overlaps with row #{1}").format(d.idx, previous.idx))
			previous = d

	def validate_accounts(self):
		companies = set()
		for d in self.get("accounts"):
			# BR-003
			if d.company in companies:
				frappe.throw(_("Company {0} is listed more than once").format(frappe.bold(d.company)))
			companies.add(d.company)

			# BR-004
			account = frappe.db.get_value(
				"Account", d.account, ["root_type", "is_group", "company"], as_dict=True
			)
			if not account:
				frappe.throw(_("Row #{0}: Account {1} does not exist").format(d.idx, d.account))
			if account.company != d.company:
				frappe.throw(
					_("Row #{0}: Account {1} does not belong to company {2}").format(
						d.idx, frappe.bold(d.account), frappe.bold(d.company)
					)
				)
			if account.root_type != "Asset" or account.is_group:
				frappe.throw(
					_(
						"Row #{0}: TCS on purchases is a receivable - select an Asset (non-group) account for {1}"
					).format(d.idx, frappe.bold(d.account))
				)

	# ------------------------------------------------------------------
	# Resolvers used by the Purchase Invoice engine (Sheet 10, steps 2 to 4)
	# ------------------------------------------------------------------
	def validate_usable_on(self, posting_date):
		"""BR-010 / BR-013: the category must be active and within its window."""
		posting_date = getdate(posting_date)

		if not self.is_active:
			frappe.throw(
				_("TCS Category {0} is inactive and cannot be used on a new invoice").format(
					frappe.bold(self.name)
				)
			)

		if self.effective_to and posting_date > getdate(self.effective_to):
			frappe.throw(
				_("TCS Category {0} expired on {1}").format(
					frappe.bold(self.name), formatdate(self.effective_to)
				)
			)

		if self.effective_from and posting_date < getdate(self.effective_from):
			frappe.throw(
				_("TCS Category {0} is effective only from {1}").format(
					frappe.bold(self.name), formatdate(self.effective_from)
				)
			)

	def get_company_account(self, company):
		"""BR-011: the TCS Account row for the invoice's company."""
		for row in self.accounts:
			if row.company == company:
				return row.account

		frappe.throw(
			_("No TCS account is configured for company {0} on category {1}").format(
				frappe.bold(company), frappe.bold(self.name)
			)
		)

	def get_applicable_rate_row(self, posting_date):
		"""BR-012: the TCS Rate row covering the posting date."""
		posting_date = getdate(posting_date)
		for row in self.rates:
			if getdate(row.from_date) <= posting_date <= getdate(row.to_date):
				return row

		frappe.throw(
			_("No TCS rate is configured for {0} on category {1}").format(
				formatdate(posting_date), frappe.bold(self.name)
			)
		)
