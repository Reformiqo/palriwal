# Copyright (c) 2026, Reformiqo and contributors
# For license information, please see license.txt

"""Site tests for the TCS Category master (TC-001 to TC-007).

Run with: bench --site <site> run-tests --app palriwal --doctype "TCS Category"
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_years, getdate


class TestTCSCategory(FrappeTestCase):
	def setUp(self):
		self.company = frappe.db.get_value("Company", {"country": "India"}) or frappe.db.get_value(
			"Company", {}
		)
		self.asset_account = frappe.db.get_value(
			"Account", {"company": self.company, "root_type": "Asset", "is_group": 0}
		)
		self.liability_account = frappe.db.get_value(
			"Account", {"company": self.company, "root_type": "Liability", "is_group": 0}
		)

	def make_category(self, **kwargs):
		doc = frappe.get_doc(
			{
				"doctype": "TCS Category",
				"category_name": kwargs.get("category_name", "_Test TCS Category"),
				"statutory_section": "206C(1)",
				"nature_of_collection": "Scrap",
				"form_27eq_code": "E",
				"calculation_base": "Grand Total",
				"rates": kwargs.get(
					"rates",
					[
						{
							"from_date": "2026-04-01",
							"to_date": "2027-03-31",
							"tax_rate": 1,
							"single_threshold": 0,
							"cumulative_threshold": 5000000,
						}
					],
				),
				"accounts": kwargs.get(
					"accounts", [{"company": self.company, "account": self.asset_account}]
				),
			}
		)
		return doc

	def tearDown(self):
		frappe.db.rollback()

	def test_tc001_create(self):
		doc = self.make_category().insert()
		self.assertEqual(doc.name, "_Test TCS Category")

	def test_tc002_overlapping_rate_periods(self):
		doc = self.make_category(
			rates=[
				{"from_date": "2026-04-01", "to_date": "2027-03-31", "tax_rate": 1},
				{"from_date": "2027-01-01", "to_date": "2028-03-31", "tax_rate": 1},
			]
		)
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_tc004_duplicate_company(self):
		doc = self.make_category(
			accounts=[
				{"company": self.company, "account": self.asset_account},
				{"company": self.company, "account": self.asset_account},
			]
		)
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_tc005_wrong_account_type(self):
		if not self.liability_account:
			return
		doc = self.make_category(accounts=[{"company": self.company, "account": self.liability_account}])
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_payable_account_must_be_liability(self):
		doc = self.make_category(
			accounts=[
				{
					"company": self.company,
					"account": self.asset_account,
					"payable_account": self.asset_account,
				}
			]
		)
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_at_least_one_account_per_row(self):
		doc = self.make_category(accounts=[{"company": self.company}])
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_tc006_invalid_rate(self):
		doc = self.make_category(
			rates=[{"from_date": "2026-04-01", "to_date": "2027-03-31", "tax_rate": 150}]
		)
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_br008_negative_threshold(self):
		doc = self.make_category(
			rates=[
				{"from_date": "2026-04-01", "to_date": "2027-03-31", "tax_rate": 1, "single_threshold": -1}
			]
		)
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_br005_effective_window(self):
		doc = self.make_category()
		doc.effective_from = "2026-04-01"
		doc.effective_to = "2026-03-31"
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_resolvers(self):
		doc = self.make_category().insert()
		self.assertEqual(doc.get_applicable_rate_row("2026-06-15").tax_rate, 1)
		self.assertEqual(doc.get_company_account(self.company), self.asset_account)
		# sales side not mapped on this row
		self.assertRaises(frappe.ValidationError, doc.get_company_account, self.company, "Customer")
		self.assertRaises(frappe.ValidationError, doc.get_applicable_rate_row, "2025-06-15")
		self.assertRaises(frappe.ValidationError, doc.get_company_account, "_No Such Company")

		doc.effective_to = "2026-03-31"
		self.assertRaises(frappe.ValidationError, doc.validate_usable_on, "2026-06-15")
		doc.effective_to = None
		doc.is_active = 0
		self.assertRaises(frappe.ValidationError, doc.validate_usable_on, "2026-06-15")
