// Copyright (c) 2026, Reformiqo and contributors
// For license information, please see license.txt

frappe.query_reports["TCS Computation Summary"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "party_type",
			label: __("Party Type"),
			fieldtype: "Select",
			options: ["Supplier", "Customer"],
			default: "Supplier",
			reqd: 1,
			on_change() {
				frappe.query_report.set_filter_value("party", "");
			},
		},
		{
			fieldname: "party",
			label: __("Party"),
			fieldtype: "Dynamic Link",
			get_options() {
				return frappe.query_report.get_filter_value("party_type");
			},
		},
		{
			fieldname: "fiscal_year",
			label: __("Fiscal Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today()),
			on_change() {
				const fy = frappe.query_report.get_filter_value("fiscal_year");
				if (!fy) return;
				frappe.model.with_doc("Fiscal Year", fy, function () {
					const doc = frappe.model.get_doc("Fiscal Year", fy);
					frappe.query_report.set_filter_value({
						from_date: doc.year_start_date,
						to_date: doc.year_end_date,
					});
				});
			},
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today(), true)[1],
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "tcs_category",
			label: __("TCS Category"),
			fieldtype: "Link",
			options: "TCS Category",
		},
		{
			fieldname: "threshold_status",
			label: __("Threshold Status"),
			fieldtype: "Select",
			options: [
				"",
				"Below Single and Cumulative",
				"Single Threshold Crossed",
				"Cumulative Threshold Crossed",
				"No Threshold Configured",
			],
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.is_total_row) {
			value = `<b>${value}</b>`;
		} else if (column.fieldname === "party_pan" && data && !data.party_pan && data.party) {
			// Blank PAN highlighted - needed for Form 26AS / 27EQ matching
			value = `<span class="indicator-pill red">${__("Missing")}</span>`;
		}
		return value;
	},
};
