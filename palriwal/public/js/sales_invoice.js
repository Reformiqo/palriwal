// Palriwal customisations for the Sales Invoice form.
//
// This file merges the two Client Scripts that previously lived in the site
// database (DocType: Sales Invoice, Apply To: Form):
//
//   1. "SALES INVOICE"  (last series no. pop up)
//      Shows an intro banner with the last document created in the currently
//      selected naming series.
//
//   2. "SALES INVOICE = COMPANY WISE SERIES BIFURGATION IN LIST DROPDOWN"
//      Restricts the naming_series dropdown to the series allowed for the
//      selected company.
//
// Loaded through hooks.py -> doctype_js.
//
// IMPORTANT: disable (or delete) the two original Client Scripts on the site.
// If they stay enabled, both the database copy and this file register handlers
// on the same events and every action runs twice.

(function () {
	// -----------------------------------------------------------------
	// 1. Last entry in the selected naming series
	// -----------------------------------------------------------------

	const FILTER_BY_COMPANY = true; // set false if a series is shared across companies

	function series_to_like_pattern(series) {
		if (!series) return null;
		return (
			series
				.replace(/\.#+\./g, "%") // .#####.
				.replace(/\.(YYYY|YY|MMMM|MM|DD|WW|FY)\./g, "%") // .YY. .FY. etc
				.replace(/#+/g, "%") // stray #####
				.replace(/\./g, "") + // leftover dots
			"%"
		);
	}

	function show_last_series_entry(frm) {
		// always wipe the previous message first — nothing ever stacks
		frm.set_intro(null);
		frm.__series_token = (frm.__series_token || 0) + 1;
		const token = frm.__series_token;

		if (!frm.is_new() || !frm.doc.naming_series) return;

		const series = frm.doc.naming_series;
		const filters = { name: ["like", series_to_like_pattern(series)] };
		if (FILTER_BY_COMPANY && frm.doc.company) filters.company = frm.doc.company;

		frappe.db
			.get_list("Sales Invoice", {
				filters: filters,
				fields: ["name", "creation"],
				order_by: "name desc", // <-- highest number, not latest created
				limit: 1,
			})
			.then((r) => {
				if (token !== frm.__series_token) return; // a newer call superseded this one

				if (!r || !r.length) {
					frm.set_intro(__('No entries yet in "{0}" series.', [series]), "blue");
					return;
				}

				const d = r[0];
				const link = `<a href="/app/sales-invoice/${encodeURIComponent(d.name)}"
                         target="_blue"><b>${frappe.utils.escape_html(d.name)}</b></a>`;

				frm.set_intro(
					__('Last entry in "{0}" series: {1} (created {2})', [
						series,
						link,
						frappe.datetime.comment_when(d.creation),
					]),
					"blue"
				);
			});
	}

	// -----------------------------------------------------------------
	// 2. Company-wise naming series bifurcation
	// -----------------------------------------------------------------

	const COMPANY_NAMING_SERIES = {
		"Jay Ambey Traders": [
			"HAZ/.#####./26-27",
			"CN-.#####.-26-27",
			"DN-.#####.-26-27",
			"HAZ/.#####./25-26",
			"TI/.#####./25-26",
			"CN/.#####./25-26",
			"DN/.#####./25-26",
			"OTH/.#####./25-26",
			"SRET-.YY.-",
		],
		"PALRIWAL METALS AND MINERALS PRIVATE LIMITED": ["INV/.26-27./", "SINV-.YY.-"],
	};

	function apply_company_naming_series(frm) {
		// naming_series is only editable before the first save
		if (!frm.is_new()) return;

		const options = COMPANY_NAMING_SERIES[frm.doc.company] || [];
		if (options.length === 0) return; // no restriction if company not mapped

		frm.set_df_property("naming_series", "options", options.join("\n"));
		frm.refresh_field("naming_series");

		// Reset only if the current pick is invalid for this company
		if (!options.includes(frm.doc.naming_series)) {
			frm.set_value("naming_series", options[0]);
		}
	}

	// -----------------------------------------------------------------
	// Handlers
	// -----------------------------------------------------------------

	frappe.ui.form.on("Sales Invoice", {
		onload_post_render(frm) {
			apply_company_naming_series(frm);
		},
		refresh(frm) {
			// Order matters: apply_company_naming_series() may change naming_series,
			// so the banner is drawn after it to reflect the final value. The token
			// guard in show_last_series_entry() discards any superseded lookup.
			apply_company_naming_series(frm);
			show_last_series_entry(frm);
		},
		company(frm) {
			apply_company_naming_series(frm);
			show_last_series_entry(frm);
		},
		naming_series(frm) {
			show_last_series_entry(frm);
		},
	});
})();
