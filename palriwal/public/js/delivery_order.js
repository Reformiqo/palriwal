// Copyright (c) 2026, Reformiqo and contributors
// For license information, please see license.txt

// Delivery Order is a site-level custom DocType, and Frappe does not load doctype_js for
// custom DocTypes, so this file is included on every desk page (hooks.py app_include_js).
//
// Buttons on a submitted Delivery Order:
//   Create Delivery Note - partial quantities, at most the pending quantity per row
//   Create Payment       - same as the "Making Payment Entry from Delivery Out" Client Script
// All quantities and checks are computed on the server (palriwal.palriwal.delivery_order).

(function () {
	const API = "palriwal.palriwal.delivery_order.delivery_order.";
	const QTY_COLUMNS = ["custom_delivered_qty", "custom_pending_qty"];

	frappe.ui.form.on("Delivery Order", {
		refresh(frm) {
			show_qty_columns(frm);
			if (frm.doc.docstatus !== 1) return;

			show_delivery_summary(frm);

			if (frm.doc.custom_delivery_status !== "Fully Delivered") {
				frm.add_custom_button(__("Create Delivery Note"), () => create_delivery_note(frm));
			}

			if (frm.doc.purchase_order) {
				frm.add_custom_button(__("Create Payment"), () => create_payment(frm));
			}
		},
	});

	// Delivered / Pending Qty are Purchase Order Item fields shown only for Delivery Orders,
	// so they are put in the grid here rather than in the Purchase Order Item list view.
	function show_qty_columns(frm) {
		const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
		if (!grid || grid.__palriwal_qty_columns) return;
		grid.__palriwal_qty_columns = true;

		let changed = false;
		(grid.docfields || []).forEach((df) => {
			if (QTY_COLUMNS.includes(df.fieldname)) {
				df.in_list_view = 1;
				df.columns = 1;
				changed = true;
			} else if (df.fieldname === "schedule_date") {
				// same as the header Required By; makes room for the two quantity columns
				df.in_list_view = 0;
			}
		});
		if (changed && grid.reset_grid) grid.reset_grid();
	}

	function show_delivery_summary(frm) {
		const status = frm.doc.custom_delivery_status;
		if (!status) return;
		const color =
			{ "Fully Delivered": "green", "Partly Delivered": "orange" }[status] || "red";
		frm.dashboard.add_indicator(__(status), color);
		frm.dashboard.add_indicator(
			__("Delivered: {0}", [format_number(frm.doc.custom_total_delivered_qty || 0)]),
			"blue"
		);
		frm.dashboard.add_indicator(
			__("Pending: {0}", [format_number(frm.doc.custom_total_pending_qty || 0)]),
			frm.doc.custom_total_pending_qty > 0 ? "orange" : "green"
		);
	}

	function create_delivery_note(frm) {
		frappe
			.call({
				method: API + "get_delivery_order_items",
				args: { delivery_order: frm.doc.name },
			})
			.then((r) => {
				const status = r.message;
				if (!status || status.pending_qty <= 0) {
					frappe.msgprint(
						__("Delivery Order {0} is already fully delivered.", [frm.doc.name])
					);
					frm.reload_doc();
					return;
				}
				show_delivery_dialog(
					frm,
					status.rows.filter((row) => row.pending_qty > 0)
				);
			});
	}

	function show_delivery_dialog(frm, rows) {
		const dialog = new frappe.ui.Dialog({
			title: __("Create Delivery Note"),
			size: "extra-large",
			fields: [
				{
					fieldname: "customer",
					fieldtype: "Link",
					options: "Customer",
					label: __("Customer"),
					description: __("Optional here; can also be set on the Delivery Note."),
				},
				{
					fieldname: "items",
					fieldtype: "Table",
					label: __("Items"),
					cannot_add_rows: true,
					cannot_delete_rows: true,
					in_place_edit: true,
					data: rows.map((row) => ({
						name_: row.name,
						item_code: row.item_code,
						uom: row.uom,
						order_qty: row.qty,
						delivered_qty: row.delivered_qty,
						pending_qty: row.pending_qty,
						qty: row.pending_qty,
					})),
					fields: [
						{ fieldname: "name_", fieldtype: "Data", hidden: 1 },
						{
							fieldname: "item_code",
							fieldtype: "Link",
							options: "Item",
							label: __("Item"),
							read_only: 1,
							in_list_view: 1,
							columns: 3,
						},
						{
							fieldname: "uom",
							fieldtype: "Data",
							label: __("UOM"),
							read_only: 1,
							in_list_view: 1,
							columns: 1,
						},
						{
							fieldname: "order_qty",
							fieldtype: "Float",
							label: __("Delivery Order Qty"),
							read_only: 1,
							in_list_view: 1,
							columns: 1,
						},
						{
							fieldname: "delivered_qty",
							fieldtype: "Float",
							label: __("Delivered Qty"),
							read_only: 1,
							in_list_view: 1,
							columns: 1,
						},
						{
							fieldname: "pending_qty",
							fieldtype: "Float",
							label: __("Pending Qty"),
							read_only: 1,
							in_list_view: 1,
							columns: 2,
						},
						{
							fieldname: "qty",
							fieldtype: "Float",
							label: __("Qty to Deliver"),
							in_list_view: 1,
							reqd: 1,
							columns: 2,
						},
					],
				},
			],
			primary_action_label: __("Create"),
			primary_action(values) {
				const items = (values.items || [])
					.filter((row) => flt(row.qty) > 0)
					.map((row) => ({ name: row.name_, qty: flt(row.qty) }));
				if (!items.length) {
					frappe.msgprint(__("Enter a quantity to deliver for at least one item."));
					return;
				}
				const over = (values.items || []).filter(
					(row) => flt(row.qty) > flt(row.pending_qty)
				);
				if (over.length) {
					frappe.msgprint(
						__("Qty to Deliver cannot be more than the Pending Qty ({0}).", [
							over.map((row) => `${row.item_code}: ${row.pending_qty}`).join(", "),
						])
					);
					return;
				}
				dialog.hide();
				frappe
					.call({
						method: API + "make_delivery_note",
						args: {
							source_name: frm.doc.name,
							items: JSON.stringify(items),
							customer: values.customer || null,
						},
						freeze: true,
						freeze_message: __("Creating Delivery Note..."),
					})
					.then((r) => {
						if (!r.message) return;
						frappe.model.sync(r.message);
						frappe.get_doc(
							r.message.doctype,
							r.message.name
						).__run_link_triggers = true;
						frappe.set_route("Form", r.message.doctype, r.message.name);
					});
			},
		});
		dialog.show();
	}

	function create_payment(frm) {
		frappe.call({
			method: API + "make_payment_entry",
			args: { delivery_order: frm.doc.name },
			freeze: true,
			freeze_message: __("Creating Payment Entry..."),
			callback(r) {
				if (!r.message) return;
				frappe.msgprint({
					title: __("Payment Entry"),
					message: __("Payment Entry: {0}", [
						`<a href="/app/payment-entry/${encodeURIComponent(
							r.message
						)}">${frappe.utils.escape_html(r.message)}</a>`,
					]),
					indicator: "green",
				});
			},
		});
	}

	function format_number(value) {
		return frappe.format(value, { fieldtype: "Float" });
	}

	frappe.provide("frappe.listview_settings");
	frappe.listview_settings["Delivery Order"] = Object.assign(
		frappe.listview_settings["Delivery Order"] || {},
		{
			add_fields: ["custom_delivery_status", "custom_total_pending_qty"],
			get_indicator(doc) {
				if (doc.docstatus !== 1 || !doc.custom_delivery_status) return;
				const color =
					{ "Fully Delivered": "green", "Partly Delivered": "orange" }[
						doc.custom_delivery_status
					] || "red";
				return [
					__(doc.custom_delivery_status),
					color,
					`custom_delivery_status,=,${doc.custom_delivery_status}`,
				];
			},
		}
	);
})();
