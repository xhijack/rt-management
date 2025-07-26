// File: apps/your_app/public/js/laporan_uang_masuk_d.js

frappe.pages['laporan-uang-masuk-d'].on_page_load = function(wrapper) {
    // 1. Buat page
    let page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Laporan Uang Masuk dan Keluar',
        single_column: true
    });

    // 2. Hapus field sebelumnya (jika hot-reload)
    page.clear_fields();

    // 3. Container filter
    let $filter_area = $(`
        <form class="form-inline frappe-control mb-3">
            <div class="filter-row"></div>
        </form>
    `).appendTo(page.main);

    // 4. Tambah filter fields
    page.add_field({
        label: 'From Date',
        fieldtype: 'Date',
        fieldname: 'from_date',
        default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
        reqd: 1,
        change: load_data
    }, $filter_area.find('.filter-row'));

    page.add_field({
        label: 'To Date',
        fieldtype: 'Date',
        fieldname: 'to_date',
        default: frappe.datetime.get_today(),
        reqd: 1,
        change: load_data
    }, $filter_area.find('.filter-row'));

    page.add_field({
        label: 'Account',
        fieldtype: 'Link',
        fieldname: 'account',
        options: 'Account',
        change: load_data
    }, $filter_area.find('.filter-row'));

    // 5. Tombol Refresh
    page.set_primary_action(__('Refresh'), load_data, 'octicon octicon-sync');

    // 6. Container hasil
    page.main.append(`
        <div class="section card mb-3 p-3">
            <h5>Saldo Awal</h5>
            <div id="opening-balance" class="text-right font-weight-bold"></div>
        </div>
        <div class="section card mb-3 p-3">
            <h5>Uang Masuk</h5>
            <div id="uang-masuk"></div>
        </div>
        <div class="section card mb-3 p-3">
            <h5>Uang Keluar</h5>
            <div id="uang-keluar"></div>
        </div>
        <div class="section card mb-3 p-3">
            <h5>Uang Sisa</h5>
            <div id="uang-sisa" class="text-right font-weight-bold"></div>
        </div>
    `);

    // 7. Fungsi fetch data
    function load_data() {
        const args = page.get_form_values();
        frappe.call({
            method: 'rt_management.rt_management.page.laporan_uang_masuk_d.laporan_uang_masuk_d.get_data',
            args: args,
            callback: r => {
                if(r.message) {
                    render({
                        opening:  r.message.opening,
                        incoming: r.message.in,
                        outgoing: r.message.out,
                        balance:  r.message.balance
                    });
                } else {
                    frappe.msgprint(__('Data tidak ditemukan.'));
                }
            }
        });
    }

    // 8. Fungsi render hasil
    function render(data) {
        // Saldo Awal
        $('#opening-balance').html(
            frappe.format(data.opening, { fieldtype:'Currency' })
        );

        // Uang Masuk + footer total
        const totalIn = data.incoming.reduce((sum, r) => sum + r.total, 0);
        $('#uang-masuk').html(build_table(data.incoming, 'income_account', totalIn));

        // Uang Keluar + footer total
        const totalOut = data.outgoing.reduce((sum, r) => sum + r.total, 0);
        $('#uang-keluar').html(build_table(data.outgoing, 'expense_account', totalOut));

        // Uang Sisa
        $('#uang-sisa').html(
            frappe.format(data.balance, { fieldtype:'Currency' })
        );
    }

    // 9. Helper bikin tabel dengan footer Total
    function build_table(rows, key, grandTotal) {
        let html = `
            <table class="table table-striped table-hover table-bordered">
                <thead class="thead-light">
                    <tr>
                        <th>Akun</th>
                        <th class="text-right">Jumlah</th>
                    </tr>
                </thead>
                <tbody>`;
        if (!rows.length) {
            html += `<tr><td colspan="2" class="text-center text-muted">— Tidak ada data —</td></tr>`;
        } else {
            rows.forEach(r => {
                const acc = r[key];
                html += `
                    <tr>
                        <td>
                            <a href="#/desk/Form/Account/${encodeURIComponent(acc)}" target="_blank">
                                ${acc}
                            </a>
                        </td>
                        <td class="text-right">${frappe.format(r.total, {fieldtype:'Currency'})}</td>
                    </tr>`;
            });
        }
        html += `
                </tbody>
                <tfoot>
                    <tr class="font-weight-bold">
                        <td>Total</td>
                        <td class="text-right">${frappe.format(grandTotal, {fieldtype:'Currency'})}</td>
                    </tr>
                </tfoot>
            </table>`;
        return html;
    }

    // 10. Load pertama kali
    load_data();
};
