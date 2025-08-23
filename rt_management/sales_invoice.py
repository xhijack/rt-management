import requests
import frappe
from frappe.utils import formatdate, getdate
from frappe.utils.pdf import get_pdf
from frappe.utils import fmt_money
from frappe.utils import getdate, add_months, today



def send_invoice_pdf_via_telegram(docname, telegram_user_id):
    """
    Background job: render Sales Invoice ke PDF dan kirim via Telegram.
    """
    # 1. Load dokumen
    doc = frappe.get_doc("Sales Invoice", docname)

    # 2. Ambil token bot
    bot = frappe.get_all("Telegram Bot", pluck="name")
    if not bot:
        frappe.log_error("Telegram Bot belum dikonfigurasi", "send_invoice_pdf_via_telegram")
        return
    token = frappe.get_doc("Telegram Bot", bot[0]).get_password("api_token")

    # 3. Render HTML & generate PDF
    html = frappe.get_print("Sales Invoice", docname,
                            print_format="Sales Invoice", doc=doc, no_letterhead=1)
    pdf_bytes = get_pdf(html)

    # 4. Kirim file ke Telegram
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    files = {
        "document": (f"{docname}.pdf", pdf_bytes, "application/pdf")
    }

    month_names_id = [
        "Januari", "Februari", "Maret", "April", "Mei", "Juni",
        "Juli", "Agustus", "September", "Oktober", "November", "Desember"
    ]

    date_obj = getdate(doc.posting_date)     # Lihat dokumentasi Frappe tentang getdate
    # month_year = date_obj.strftime("%B %Y")  # :contentReference[oaicite:2]{index=2}
    bulan = month_names_id[date_obj.month - 1]
    month_year_id = f"{bulan} {date_obj.year}"  # contoh: "Juli 2025"

    data = {
        "chat_id": telegram_user_id,
        "caption": (
            f"Assalamualaikum Bapak/Ibu {doc.customer_name},\n\n"
            f"Berikut adalah tagihan Iuran {doc.company} di Bulan {month_year_id} Anda:\n"
            f"🔔 *No. Inv {docname}* sebesar Rp {doc.grand_total:,.2f}"
        ),
        "parse_mode": "Markdown"
    }

    try:
        resp = requests.post(url, data=data, files=files, timeout=60)
        resp.raise_for_status()
    except Exception as e:
        frappe.log_error(f"Error kirim Telegram for {docname}: {e}", "send_invoice_pdf_via_telegram")

def on_submit(doc, method):
    """
    Hook Sales Invoice on_submit: enqueue task untuk generate PDF & kirim ke Telegram.
    """
    user_info = get_telegram_user_by_customer(doc.customer)
    if not user_info:
        return

    # Enqueue background job
    frappe.enqueue(
        method="rt_management.sales_invoice.send_invoice_pdf_via_telegram",
        queue="long",
        timeout=1500,
        is_async=True,
        docname=doc.name,
        telegram_user_id=user_info.get("telegram_user_id")
    )




def send_notif_when_payment_entry_created(docname, telegram_user_id):
    doc = frappe.get_doc('Payment Entry', docname)
    bot = frappe.get_all("Telegram Bot", pluck="name")
    if not bot:
        frappe.log_error("Telegram Bot belum dikonfigurasi", "send_invoice_pdf_via_telegram")
        return
    token = frappe.get_doc("Telegram Bot", bot[0]).get_password("api_token")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {
        "chat_id": telegram_user_id,
        "text": 
            f"Kami konfirmasi pembayaran Iuran sebesar {fmt_money(doc.paid_amount, currency='IDR')} sudah kami terima di tanggal {doc.posting_date}\nKami ucapkan terima kasih"
        ,
        "parse_mode": "Markdown"
    }

    try:
        requests.post(url,json=data)
    except Exception as e:
        frappe.log_error(f"Error kirim Telegram for {doc.name}: {e}", "send_invoice_pdf_via_telegram")


def payment_on_submit(doc, method):
    user_info = get_telegram_user_by_customer(doc.party)
    if not user_info:
        return

    frappe.enqueue(
        method="rt_management.sales_invoice.send_notif_when_payment_entry_created",
        queue="long",
        timeout=1500,
        is_async=True,
        docname=doc.name,
        telegram_user_id=user_info.get("telegram_user_id")
    )


def get_telegram_user_by_customer(customer_id: str):
    """
    Ambil Telegram User record yang terhubung dengan Customer tertentu.
    Parameter:
        customer_id (str): nama (ID) Customer di ERPNext
    Return:
        dict: {
            "customer_id": str,
            "customer_name": str,
            "system_user": str,
            "telegram_user_doc": str,
            "telegram_user_id": str
        } atau {} jika tidak ada
    """
    result = frappe.db.sql("""
        SELECT
            c.name                 AS customer_id,
            c.customer_name        AS customer_name,
            pu.user                AS system_user,
            tu.name                AS telegram_user_doc,
            tu.telegram_user_id    AS telegram_user_id
        FROM `tabCustomer` c
        LEFT JOIN `tabPortal User` pu
            ON pu.parent = c.name
            AND pu.parenttype = 'Customer'
        LEFT JOIN `tabUser` u
            ON u.name = pu.user
        LEFT JOIN `tabTelegram User` tu
            ON tu.user = u.name
        WHERE c.name = %s
        LIMIT 1
    """, (customer_id,), as_dict=True)  # Raw SQL dengan dict output :contentReference[oaicite:0]{index=0}

    # Kembalikan record pertama jika ada, atau dict kosong
    return result[0] if result else {}



@frappe.whitelist(allow_guest=True)
def get_sales_invoice_list(from_date=None, to_date=None):
    from frappe.utils import getdate, today, add_months, flt

    try:
        # Default range: 25 (dua bulan sebelumnya) s/d 10 (bulan berjalan)
        if not from_date or not to_date:
            today_date = getdate(today())
            default_to_date = today_date.replace(day=10)
            default_from_date = add_months(default_to_date, -2).replace(day=25)
            from_date = from_date or default_from_date
            to_date = to_date or default_to_date
        else:
            from_date = getdate(from_date)
            to_date = getdate(to_date)

        # Ambil invoice
        invoices = frappe.get_all(
            "Sales Invoice",
            fields=["name", "customer", "grand_total", "outstanding_amount", "posting_date"],
            filters={"docstatus": 1, "posting_date": ["between", [from_date, to_date]]},
            order_by="posting_date desc"
        )

        if not invoices:
            return {"success": True, "data": []}

        inv_names = [inv.name for inv in invoices]

        # --- Cari Payment Entry draft yang merefer ke SI (batch, hemat query) ---
        # 1) Ambil semua child Payment Entry Reference yang mengacu ke daftar SI
        refs = frappe.get_all(
            "Payment Entry Reference",
            fields=["parent", "reference_name"],
            filters={
                "reference_doctype": "Sales Invoice",
                "reference_name": ["in", inv_names]
            },
            distinct=True
        )
        parent_pes = list({r.parent for r in refs}) if refs else []

        draft_pe_names = set()
        if parent_pes:
            # 2) Ambil Payment Entry yang statusnya draft (docstatus=0) dari parent di atas
            draft_pe_names = set(frappe.get_all(
                "Payment Entry",
                filters={"name": ["in", parent_pes], "docstatus": 0},
                pluck="name"
            ))

        # 3) Kembalikan daftar SI yang sedang "ditunggu konfirmasi" (punya PE draft)
        invoices_with_draft_pe = set(
            r.reference_name for r in refs if r.parent in draft_pe_names
        )

        # --- Ambil units (distinct) untuk semua invoice sekaligus ---
        # Catatan: gunakan distinct=True, jangan "DISTINCT unit" di fields.
        unit_rows = frappe.get_all(
            "Sales Invoice Item",
            fields=["parent", "unit"],
            filters={"parent": ["in", inv_names]},
            distinct=True
        )
        units_map = {}
        for row in unit_rows:
            if row.unit:
                units_map.setdefault(row.parent, []).append(row.unit)

        # Build result
        result = []
        for inv in invoices:
            if inv.name in invoices_with_draft_pe:
                payment_status = "Tunggu konfirmasi"
            else:
                payment_status = "Paid" if flt(inv.outstanding_amount) == 0 else "Unpaid"

            result.append({
                "invoice": inv.name,
                "customer": inv.customer,
                "total": inv.grand_total,
                "status": payment_status,
                "posting_date": inv.posting_date,
                "units": units_map.get(inv.name, [])
            })

        return {"success": True, "data": result}

    except Exception:
        frappe.log_error(title="Sales Invoice List Error", message=frappe.get_traceback())
        return {"success": False, "error": _("Terjadi kesalahan. Lihat Error Log untuk detailnya.")}
