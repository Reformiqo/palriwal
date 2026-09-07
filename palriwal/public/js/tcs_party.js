// Palriwal TCS engine - Supplier and Customer forms.
// BR-009 / FR-011: only active TCS Categories are selectable.
// Loaded through hooks.py -> doctype_js for both party doctypes; the guard keeps the
// handlers from being registered twice when both forms are opened in one session.

(function () {
	if (window.__palriwal_tcs_party_loaded) return;
	window.__palriwal_tcs_party_loaded = true;

	["Supplier", "Customer"].forEach((doctype) => {
		frappe.ui.form.on(doctype, {
			setup(frm) {
				frm.set_query("custom_tcs_category", () => ({ filters: { is_active: 1 } }));
			},
		});
	});
})();
