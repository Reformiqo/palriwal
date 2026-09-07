# Copyright (c) 2026, Reformiqo and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class TCSRate(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		cumulative_threshold: DF.Currency
		from_date: DF.Date
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		single_threshold: DF.Currency
		tax_rate: DF.Percent
		to_date: DF.Date
	# end: auto-generated types

	pass
