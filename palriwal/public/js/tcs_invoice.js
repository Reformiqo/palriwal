// Palriwal TCS engine - Purchase Invoice and Sales Invoice forms (FRD v3.0, Sheet 10).
//
//   party changed         -> default the category from the supplier / customer, set Apply TCS (BR-014)
//   Apply TCS toggled     -> recalculate; unticked removes the engine row and clears fields
//   TCS Category changed  -> recalculate from scratch against the new category
//   posting_date changed  -> re-resolve the rate row and recalculate
//
// Every recalculation asks the server (palriwal.palriwal.tcs.engine.get_tcs_details) so the
// form and the save use one and the same algorithm. The server-side validate is still the
// authority - whatever the form shows is recomputed on save.
//
// Loaded through hooks.py -> doctype_js for both invoice doctypes; the guard keeps the
// handlers from being registered twice when both forms are opened in one session.

(function () {
	if (window.__palriwal_tcs_invoice_loaded) return;
	window.__palriwal_tcs_invoice_loaded = true;

	const INVOICES = [
		{
			doctype: "Purchase Invoice",
			party_type: "Supplier",
			party_field: "supplier",
			taxes_doctype: "Purchase Taxes and Charges",
		},
		{
			doctype: "Sales Invoice",
			party_type: "Customer",
			party_field: "customer",
			taxes_doctype: "Sales Taxes and Charges",
		},
	];

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

	function recalculate(frm, cfg) {
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

		if (!frm.doc.company || !frm.doc.posting_date || !frm.doc[cfg.party_field]) return;

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

	function fetch_party_category(frm, cfg, callback) {
		frappe.call({
			method: "palriwal.palriwal.tcs.engine.get_party_tcs_category",
			args: { party_type: cfg.party_type, party: frm.doc[cfg.party_field] },
			callback(r) {
				callback(r.message || null);
			},
		});
	}

	function default_from_party(frm, cfg) {
		if (!frm.is_new() || frm.doc.docstatus !== 0) return;

		if (!frm.doc[cfg.party_field]) {
			frm.doc.custom_apply_tcs = 0;
			frm.doc.custom_tcs_category = null;
			frm.refresh_field("custom_apply_tcs");
			frm.refresh_field("custom_tcs_category");
			recalculate(frm, cfg);
			return;
		}

		fetch_party_category(frm, cfg, (category) => {
			// BR-014: ticked when the party has a category, otherwise not
			frm.doc.custom_apply_tcs = category ? 1 : 0;
			frm.doc.custom_tcs_category = category;
			frm.refresh_field("custom_apply_tcs");
			frm.refresh_field("custom_tcs_category");
			recalculate(frm, cfg);
		});
	}

	function lock_engine_row(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const grid_row = frm.fields_dict.taxes.grid.get_row(cdn);
		if (!grid_row) return;
		const editable = !row.custom_is_tcs_row && frm.doc.docstatus === 0;
		LOCKED_ROW_FIELDS.forEach((f) => {
			if (grid_row.docfields.find((df) => df.fieldname === f)) {
				grid_row.toggle_editable(f, editable);
			}
		});
	}

	INVOICES.forEach((cfg) => {
		const handlers = {
			setup(frm) {
				frm.set_query("custom_tcs_category", () => ({ filters: { is_active: 1 } }));
			},

			onload(frm) {
				// A brand-new invoice that already carries a party (duplicated, mapped from an
				// order / delivery / receipt, or created from a list filter) still needs the default.
				if (
					frm.is_new() &&
					frm.doc[cfg.party_field] &&
					!frm.doc.custom_apply_tcs &&
					!frm.doc.custom_tcs_category
				) {
					default_from_party(frm, cfg);
				}
			},

			custom_apply_tcs(frm) {
				if (!frm.doc.custom_apply_tcs) {
					recalculate(frm, cfg);
					return;
				}
				if (!frm.doc.custom_tcs_category && frm.doc[cfg.party_field]) {
					fetch_party_category(frm, cfg, (category) => {
						frm.doc.custom_tcs_category = category;
						frm.refresh_field("custom_tcs_category");
						recalculate(frm, cfg);
					});
				} else {
					recalculate(frm, cfg);
				}
			},

			custom_tcs_category(frm) {
				recalculate(frm, cfg);
			},

			posting_date(frm) {
				if (frm.doc.custom_apply_tcs && frm.doc.custom_tcs_category) recalculate(frm, cfg);
			},
		};
		// supplier(frm) / customer(frm)
		handlers[cfg.party_field] = function (frm) {
			default_from_party(frm, cfg);
		};

		frappe.ui.form.on(cfg.doctype, handlers);

		frappe.ui.form.on(cfg.taxes_doctype, {
			form_render(frm, cdt, cdn) {
				lock_engine_row(frm, cdt, cdn);
			},
			taxes_remove(frm) {
				// Removing the engine row by hand is undone on save; keep the form honest now.
				if (
					frm.doc.custom_apply_tcs &&
					frm.doc.custom_tcs_category &&
					frm.doc.custom_tcs_amount &&
					!(frm.doc.taxes || []).some((d) => d.custom_is_tcs_row)
				) {
					recalculate(frm, cfg);
				}
			},
		});
	});
})();
