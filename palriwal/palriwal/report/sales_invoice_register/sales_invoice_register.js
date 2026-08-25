// Copyright (c) 2026, Reformiqo and contributors
// For license information, please see license.txt

frappe.query_reports["Sales Invoice Register"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			width: "80",
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "customer_group",
			label: __("Customer Group"),
			fieldtype: "Link",
			options: "Customer Group",
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "mode_of_payment",
			label: __("Mode of Payment"),
			fieldtype: "Link",
			options: "Mode of Payment",
		},
		{
			fieldname: "owner",
			label: __("Owner"),
			fieldtype: "Link",
			options: "User",
		},
		{
			fieldname: "cost_center",
			label: __("Cost Center"),
			fieldtype: "Link",
			options: "Cost Center",
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
		},
		{
			fieldname: "brand",
			label: __("Brand"),
			fieldtype: "Link",
			options: "Brand",
		},
		{
			fieldname: "item_group",
			label: __("Item Group"),
			fieldtype: "Link",
			options: "Item Group",
		},
		{
			fieldname: "include_payments",
			label: __("Show Ledger View"),
			fieldtype: "Check",
			default: 0,
		},
	],

	onload(report) {
		this._report = report;
	},

	// Sales Register is invoice-grain (one row per Sales Invoice), so Item
	// Code/Name/Qty (Sales Invoice Item) and Vehicle No (linked Delivery
	// Note) can't come from the report's own execute() without exploding
	// rows. Fetched client-side instead, keyed off the "Voucher"/"Delivery
	// Note" columns the report already returns, and spliced into the
	// datatable after each render — no server-side change, no new fields.
	after_datatable_render(datatable) {
		add_item_and_vehicle_columns(this._report);
	},
};

erpnext.utils.add_dimensions("Sales Invoice Register", 7);

function add_item_and_vehicle_columns(report) {
	if (!report || !report.data || !report.data.length) return;
	// already enriched this render
	if (report.columns.some((c) => c.fieldname === "item_code")) return;

	const voucher_nos = [
		...new Set(
			report.data
				.filter((d) => d.voucher_type === "Sales Invoice" && d.voucher_no)
				.map((d) => d.voucher_no),
		),
	];
	if (!voucher_nos.length) return;

	Promise.all([
		frappe.xcall("frappe.client.get_list", {
			doctype: "Sales Invoice Item",
			// "parent" here is the *parent doctype* for the child-table permission
			// check (frappe.client.get_list denies child-table reads without it) -
			// filters.parent below is the unrelated field filter on invoice name.
			parent: "Sales Invoice",
			filters: { parent: ["in", voucher_nos] },
			fields: ["parent", "item_code", "item_name", "qty"],
			limit_page_length: 0,
		}),
		// vehicle_no is an India Compliance e-Way Bill field set directly on the
		// invoice (More Info tab) - not derived via a linked Delivery Note.
		frappe.xcall("frappe.client.get_list", {
			doctype: "Sales Invoice",
			filters: { name: ["in", voucher_nos] },
			fields: ["name", "vehicle_no"],
			limit_page_length: 0,
		}),
	]).then(([items, invoices]) => {
		const by_voucher = {};
		items.forEach((row) => {
			by_voucher[row.parent] ||= { codes: [], names: [], qty: 0 };
			const bucket = by_voucher[row.parent];
			bucket.codes.push(row.item_code);
			bucket.names.push(row.item_name);
			bucket.qty += flt(row.qty);
		});

		const vehicle_by_invoice = {};
		invoices.forEach((inv) => (vehicle_by_invoice[inv.name] = inv.vehicle_no));

		report.columns.push(
			...report.prepare_columns([
				{ label: __("Item Code"), fieldname: "item_code", fieldtype: "Data", width: 140 },
				{ label: __("Item Name"), fieldname: "item_name", fieldtype: "Data", width: 160 },
				{
					label: __("Vehicle No"),
					fieldname: "vehicle_no",
					fieldtype: "Data",
					width: 120,
				},
				{ label: __("Qty"), fieldname: "qty", fieldtype: "Float", width: 90 },
			]),
		);

		report.data.forEach((row) => {
			const bucket = by_voucher[row.voucher_no];
			if (bucket) {
				row.item_code = bucket.codes.join(", ");
				row.item_name = bucket.names.join(", ");
				row.qty = bucket.qty;
			}
			row.vehicle_no = vehicle_by_invoice[row.voucher_no];
		});

		report.render_datatable();
	});
}
