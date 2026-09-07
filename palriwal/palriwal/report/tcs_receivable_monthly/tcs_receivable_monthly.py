# Copyright (c) 2026, Reformiqo and contributors
# For license information, please see license.txt

"""TCS Receivable Monthly - Purchase Invoices, the TCS Receivable asset.

Mirrors TDS Payable Monthly (FRD v3.0, Sheet 14, Report 2). Logic lives in
palriwal.palriwal.tcs.monthly_report and is shared with TCS Payable Monthly.
"""

from palriwal.palriwal.tcs import monthly_report


def execute(filters=None):
	filters = dict(filters or {})
	# the Supplier filter of this report is the generic party filter of the shared module
	filters["party"] = filters.get("supplier")
	return monthly_report.execute(filters, "Supplier")
