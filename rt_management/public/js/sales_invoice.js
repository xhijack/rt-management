frappe.ui.form.on("Sales Invoice", {
    customer: function(frm) {
        if (!frm.doc.customer) return;

        // Ambil daftar unit berdasarkan customer
        frappe.call({
            method: "rt_management.utils.get_house_filter_by_customer",
            args: {
                customer: frm.doc.customer
            },
            callback: function(r) {
                if (r.message) {
                    const allowed_units = r.message;

                    // Set filter untuk setiap baris item
                    frm.fields_dict.items.grid.get_field("unit").get_query = function(doc, cdt, cdn) {
                        return {
                            filters: [
                                ["name", "in", allowed_units]
                            ]
                        };
                    };
                }
            }
        });
    }
});
