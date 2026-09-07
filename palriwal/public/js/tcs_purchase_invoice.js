// Palriwal TCS engine - Purchase Invoice form (FRD v3.0, Sheet 10 trigger table).
//
//   supplier changed      -> default the category from the supplier, set Apply TCS (BR-014)
//   Apply TCS toggled     -> recalculate; unticked removes the engine row and clears fields
//   TCS Category changed  -> recalculate from scratch against the new category
//   posting_date changed  -> re-resolve the rate row and recalculate
//
// Every recalculation asks the server (palriwal.palriwal.tcs.engine.get_tcs_details) so the
// form and the save use one and the same algorithm. The server-side validate is still the
// authority - whatever the form shows is recomputed on save.
//
// Loaded through hooks.py -> doctype_js.

(function () {
	const TRACKING_FIELDS = [
		"custom_tcs_section",
		"custom_tcs_rate",
		"custom_tcs_base_amount",
		"custom_tcs_amount",
		"custom_tcs_threshold_status",
	];

	// Fields of the engine row the user must not edit (BR-019, Sheet 15 lock matrix)
	const LOCKED_ROW_FIELDS = [
		"category",
		"add_deduct_tax",
		"charge_type",
		"row_id",
		"account_head",
		"description",
		"rate",
		"tax_amount",
		"included_in_print_rate",
		"included_in_paid_amount",
	];

	function set_category_query(frm) {
		frm.set_query("custom_tcs_category", () => ({ filters: { is_active: 1 } }));
	}

	function remove_engine_rows(frm) {
		const rows = (frm.doc.taxes || []).filter((d) => d.custom_is_tcs_row);
		rows.forEach((d) => frappe.model.clear_doc(d.doctype, d.name));
		frm.doc.taxes = (frm.doc.taxes || []).filter((d) => !d.custom_is_tcs_row);
		frm.doc.taxes.forEach((d, i) => (d.idx = i + 1));
		return rows.length > 0;
	}

	function clear_tracking_fields(frm) {
		frm.doc.custom_tcs_section = null;
		frm.doc.custom_tcs_rate = 0;
		frm.doc.custom_tcs_base_amount = 0;
		frm.doc.custom_tcs_amount = 0;
		frm.doc.custom_tcs_threshold_status = null;
	}

	function apply_result(frm, r) {
		remove_engine_rows(frm);
		Object.assign(frm.doc, r.fields || {});
		if (r.custom_tcs_category && !frm.doc.custom_tcs_category) {
			frm.doc.custom_tcs_category = r.custom_tcs_category;
			frm.refresh_field("custom_tcs_category");
		}
		if (r.tax_row) {
			const row = frm.add_child("taxes");
			Object.assign(row, r.tax_row);
		}
		frm.refresh_field("taxes");
		TRACKING_FIELDS.forEach((f) => frm.refresh_field(f));
		// Step 15: standard totals, never recomputed by hand
		frm.cscript.calculate_taxes_and_totals();
		frm.dirty();
	}

	function recalculate(frm) {
		if (frm.doc.docstatus !== 0) return;

		frm.__tcs_token = (frm.__tcs_token || 0) + 1;
		const token = frm.__tcs_token;

		if (!frm.doc.custom_apply_tcs || !frm.doc.custom_tcs_category) {
			// Step 1 guard / BR-025: untick clears everything
			const removed = remove_engine_rows(frm);
			clear_tracking_fields(frm);
			frm.refresh_field("taxes");
			TRACKING_FIELDS.forEach((f) => frm.refresh_field(f));
			if (removed) frm.cscript.calculate_taxes_and_totals();
			return;
		}

		if (!frm.doc.company || !frm.doc.posting_date || !frm.doc.supplier) return;

		frappe.call({
			method: "palriwal.palriwal.tcs.engine.get_tcs_details",
			args: { doc: frm.doc },
			freeze: true,
			freeze_message: __("Calculating TCS..."),
			callback(r) {
				if (token !== frm.__tcs_token || !r.message) return;
				apply_result(frm, r.message);
			},
		});
	}

	function default_from_supplier(frm) {
		if (!frm.is_new() || frm.doc.docstatus !== 0) return;

		if (!frm.doc.supplier) {
			frm.doc.custom_apply_tcs = 0;
			frm.doc.custom_tcs_category = null;
			frm.refresh_field("custom_apply_tcs");
			frm.refresh_field("custom_tcs_category");
			recalculate(frm);
			return;
		}

		frappe.call({
			method: "palriwal.palriwal.tcs.engine.get_supplier_tcs_category",
			args: { supplier: frm.doc.supplier },
			callback(r) {
				const category = r.message || null;
				// BR-014: ticked when the supplier has a category, otherwise not
				frm.doc.custom_apply_tcs = category ? 1 : 0;
				frm.doc.custom_tcs_category = category;
				frm.refresh_field("custom_apply_tcs");
				frm.refresh_field("custom_tcs_category");
				recalculate(frm);
			},
		});
	}

	function lock_engine_row(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const grid_row = frm.fields_dict.taxes.grid.get_row(cdn);
		if (!grid_row) return;
		const editable = !row.custom_is_tcs_row || frm.doc.docstatus !== 0;
		LOCKED_ROW_FIELDS.forEach((f) => {
			if (grid_row.docfields.find((df) => df.fieldname === f)) {
				grid_row.toggle_editable(f, editable && frm.doc.docstatus === 0);
			}
		});
	}

	frappe.ui.form.on("Purchase Invoice", {
		setup(frm) {
			set_category_query(frm);
		},

		onload(frm) {
			// A brand-new invoice that already carries a supplier (duplicated, mapped from a
			// Purchase Order/Receipt, or created from a list filter) still needs the default.
			if (
				frm.is_new() &&
				frm.doc.supplier &&
				!frm.doc.custom_apply_tcs &&
				!frm.doc.custom_tcs_category
			) {
				default_from_supplier(frm);
			}
		},

		supplier(frm) {
			default_from_supplier(frm);
		},

		custom_apply_tcs(frm) {
			if (!frm.doc.custom_apply_tcs) {
				recalculate(frm);
				return;
			}
			if (!frm.doc.custom_tcs_category && frm.doc.supplier) {
				frappe.call({
					method: "palriwal.palriwal.tcs.engine.get_supplier_tcs_category",
					args: { supplier: frm.doc.supplier },
					callback(r) {
						frm.doc.custom_tcs_category = r.message || null;
						frm.refresh_field("custom_tcs_category");
						recalculate(frm);
					},
				});
			} else {
				recalculate(frm);
			}
		},

		custom_tcs_category(frm) {
			recalculate(frm);
		},

		posting_date(frm) {
			if (frm.doc.custom_apply_tcs && frm.doc.custom_tcs_category) recalculate(frm);
		},
	});

	frappe.ui.form.on("Purchase Taxes and Charges", {
		form_render(frm, cdt, cdn) {
			lock_engine_row(frm, cdt, cdn);
		},
		taxes_remove(frm) {
			// Removing the engine row by hand is undone on save; keep the form honest now.
			if (
				frm.doc.custom_apply_tcs &&
				frm.doc.custom_tcs_category &&
				!(frm.doc.taxes || []).some((d) => d.custom_is_tcs_row)
			) {
				if (frm.doc.custom_tcs_amount) recalculate(frm);
			}
		},
	});
})();
