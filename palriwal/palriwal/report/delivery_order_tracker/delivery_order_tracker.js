// Copyright (c) 2026, Reformiqo and contributors
// For license information, please see license.txt

frappe.query_reports["Delivery Order Tracker"] = {
	filters: [
		{
			fieldname: "view",
			label: __("View"),
			fieldtype: "Select",
			options: ["Transaction Detail", "Delivery Order Summary"],
			default: "Transaction Detail",
			reqd: 1,
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "from_date",
			label: __("From Date (DO)"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -3),
		},
		{
			fieldname: "to_date",
			label: __("To Date (DO)"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "delivery_status",
			label: __("Delivery Status"),
			fieldtype: "Select",
			options: ["", "Not Delivered", "Partly Delivered", "Fully Delivered"],
		},
		{
			fieldname: "pending_only",
			label: __("Only Rows with Pending Qty"),
			fieldtype: "Check",
		},
		{
			fieldname: "pr_status",
			label: __("Purchase Receipt Status"),
			fieldtype: "Select",
			options: ["", "Not Created", "Draft", "Submitted", "Partly Submitted"],
		},
		{
			fieldname: "purchase_order",
			label: __("Purchase Order"),
			fieldtype: "Link",
			options: "Purchase Order",
			get_query: () => ({ filters: { docstatus: 1 } }),
		},
		{
			fieldname: "delivery_order",
			label: __("Delivery Order"),
			fieldtype: "Link",
			options: "Delivery Order",
			get_query: () => ({ filters: { docstatus: 1 } }),
		},
		{
			fieldname: "supplier",
			label: __("Supplier"),
			fieldtype: "Link",
			options: "Supplier",
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "item_code",
			label: __("Item"),
			fieldtype: "Link",
			options: "Item",
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;

		const colors = {
			delivery_status: {
				"Fully Delivered": "green",
				"Partly Delivered": "orange",
				"Not Delivered": "red",
			},
			pr_status: {
				Submitted: "green",
				Draft: "orange",
				"Partly Submitted": "orange",
				"Not Created": "red",
			},
		};
		const color = colors[column.fieldname] && colors[column.fieldname][data[column.fieldname]];
		if (color) {
			value = `<span class="indicator-pill ${color}">${value}</span>`;
		} else if (column.fieldname === "pending_qty" && data.pending_qty > 0) {
			value = `<span style="color: var(--orange-600); font-weight: 600">${value}</span>`;
		} else if (column.fieldname === "not_received_qty" && data.not_received_qty > 0) {
			value = `<span style="color: var(--red-600); font-weight: 600">${value}</span>`;
		}
		return value;
	},
};
