// Copyright (c) 2026, Reformiqo and contributors
// For license information, please see license.txt

frappe.query_reports["TCS Payable Monthly"] = {
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
			fieldname: "fiscal_year",
			label: __("Fiscal Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today()),
			reqd: 1,
		},
		{
			fieldname: "from_month",
			label: __("From Month"),
			fieldtype: "Select",
			options: [
				"",
				"Jan",
				"Feb",
				"Mar",
				"Apr",
				"May",
				"Jun",
				"Jul",
				"Aug",
				"Sep",
				"Oct",
				"Nov",
				"Dec",
			],
		},
		{
			fieldname: "to_month",
			label: __("To Month"),
			fieldtype: "Select",
			options: [
				"",
				"Jan",
				"Feb",
				"Mar",
				"Apr",
				"May",
				"Jun",
				"Jul",
				"Aug",
				"Sep",
				"Oct",
				"Nov",
				"Dec",
			],
		},
		{
			fieldname: "tcs_category",
			label: __("TCS Category"),
			fieldtype: "Link",
			options: "TCS Category",
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && (data.is_total_row || data.is_subtotal_row)) {
			value = `<b>${value}</b>`;
		}
		return value;
	},
};
