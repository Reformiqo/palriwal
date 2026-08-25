# Copyright (c) 2026, Reformiqo and contributors
# For license information, please see license.txt

# Exact duplicate of the standard "Purchase Register" report, published under
# a new name so it can carry Palriwal-specific columns without touching
# erpnext's core report file. Reuses the original's _execute() as-is, so
# output is byte-for-byte identical to Purchase Register until this report is
# extended.

from erpnext.accounts.report.purchase_register.purchase_register import _execute


def execute(filters=None):
	return _execute(filters)
