// Palriwal TCS engine - Supplier form.
// BR-009 / FR-011: only active TCS Categories are selectable.
// Loaded through hooks.py -> doctype_js.

frappe.ui.form.on("Supplier", {
	setup(frm) {
		frm.set_query("custom_tcs_category", () => ({ filters: { is_active: 1 } }));
	},
});
