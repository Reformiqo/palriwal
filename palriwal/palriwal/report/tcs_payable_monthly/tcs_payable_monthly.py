# Copyright (c) 2026, Reformiqo and contributors
# For license information, please see license.txt

"""TCS Payable Monthly - Sales Invoices, the TCS Payable liability.

The sales-side twin of TCS Receivable Monthly. Logic lives in
palriwal.palriwal.tcs.monthly_report.
"""

from palriwal.palriwal.tcs import monthly_report


def execute(filters=None):
	filters = dict(filters or {})
	filters["party"] = filters.get("customer")
	return monthly_report.execute(filters, "Customer")
