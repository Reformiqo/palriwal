// Copyright (c) 2026, Reformiqo and contributors
// For license information, please see license.txt

frappe.ui.form.on("TCS Category", {
	setup(frm) {
		// BR-004: purchases post to a non-group Asset account (TCS Receivable) ...
		frm.set_query("account", "accounts", function (doc, cdt, cdn) {
			const row = locals[cdt][cdn];
			const filters = { root_type: "Asset", is_group: 0 };
			if (row.company) filters.company = row.company;
			return { filters };
		});
		// ... and sales post to a non-group Liability account (TCS Payable)
		frm.set_query("payable_account", "accounts", function (doc, cdt, cdn) {
			const row = locals[cdt][cdn];
			const filters = { root_type: "Liability", is_group: 0 };
			if (row.company) filters.company = row.company;
			return { filters };
		});
	},

	refresh(frm) {
		if (!frm.is_new() && !frm.doc.is_active) {
			frm.dashboard.set_headline(
				__("This category is inactive and cannot be selected on new invoices."),
				"orange"
			);
		}
	},
});
