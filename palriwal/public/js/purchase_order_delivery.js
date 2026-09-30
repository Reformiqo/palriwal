// Copyright (c) 2026, Reformiqo and contributors
// For license information, please see license.txt

// Purchase Order: Create > Delivery Order, same as the "Making Delivery Note from PO - N"
// Client Script, with the pending quantities and the Delivery Order built on the server
// (palriwal.palriwal.delivery_order.purchase_order). Same label and group as the Client Script,
// so while both are enabled the form shows one button (this one, it is registered first).

frappe.ui.form.on("Purchase Order", {
	refresh(frm) {
		if (frm.doc.company !== "Jay Ambey Traders" || frm.doc.docstatus !== 1) return;

		frm.add_custom_button(
			__("Delivery Order"),
			() => {
				frappe
					.call({
						method: "palriwal.palriwal.delivery_order.purchase_order.get_pending_items",
						args: { purchase_order: frm.doc.name },
					})
					.then((r) => {
						const rows = (r.message || []).filter((row) => row.pending_qty > 0);
						if (!rows.length) {
							frappe.msgprint(__("Nothing pending to deliver"));
							return;
						}
						const fields = rows.map((row, i) => ({
							fieldname: `qty_${i}`,
							fieldtype: "Float",
							label: `${row.item_name || row.item_code} (${__("Pending")}: ${
								row.pending_qty
							})`,
							default: row.pending_qty,
						}));
						frappe.prompt(
							fields,
							(values) => {
								const items = rows
									.map((row, i) => ({
										item_code: row.item_code,
										qty: flt(values[`qty_${i}`]),
									}))
									.filter((row) => row.qty > 0);
								if (!items.length) {
									frappe.msgprint(__("Please enter at least one quantity"));
									return;
								}
								frappe.call({
									method: "palriwal.palriwal.delivery_order.purchase_order.make_delivery_order",
									args: {
										purchase_order: frm.doc.name,
										items: JSON.stringify(items),
									},
									freeze: true,
									callback(res) {
										if (res.message)
											frappe.set_route(
												"Form",
												"Delivery Order",
												res.message
											);
									},
								});
							},
							__("Create Delivery Order"),
							__("Create")
						);
					});
			},
			__("Create")
		);
	},
});
