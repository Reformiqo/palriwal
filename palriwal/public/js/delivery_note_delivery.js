// Copyright (c) 2026, Reformiqo and contributors
// For license information, please see license.txt

// Delivery Note against a Delivery Order (header "Delivery Out"):
//   * the Delivery Out picker lists only submitted, not fully delivered Delivery Orders of the
//     note's company
//   * Create Purchase Receipt - opens the receipt made on submit (or makes it if missing).
//     Same label as the "Updated Creating purchase receipt ..." Client Script, whose server
//     method does not exist; while both are enabled the form shows this one.
// The receipt quantity always equals the Delivery Note quantity (server side).

frappe.ui.form.on("Delivery Note", {
	setup(frm) {
		frm.set_query("custom_delivery_out", () => {
			const filters = { docstatus: 1 };
			if (frm.doc.company) filters.company = frm.doc.company;
			if (!frm.doc.is_return) filters.custom_delivery_status = ["!=", "Fully Delivered"];
			return { filters };
		});
	},

	refresh(frm) {
		if (frm.doc.docstatus !== 1 || !frm.doc.custom_delivery_out || frm.doc.is_return) return;

		frm.add_custom_button(__("Create Purchase Receipt"), () => {
			frappe.call({
				method: "palriwal.palriwal.delivery_order.delivery_note.make_purchase_receipt",
				args: { delivery_note: frm.doc.name },
				freeze: true,
				callback(r) {
					if (r.message) frappe.set_route("Form", "Purchase Receipt", r.message);
				},
			});
		});
	},
});
