import requests
import frappe

import requests
import frappe
from frappe.utils import formatdate

from frappe.utils.pdf import get_pdf

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
    data = {
        "chat_id": telegram_user_id,
        "caption": (
            f"Assalamualaikum Bapak/Ibu {doc.customer_name},\n"
            f"Berikut adalah tagihan Anda:\n"
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
        queue="long",             # bisa pake "default" atau "long" sesuai konfigurasi
        timeout=1500,             # sesuaikan timeout (detik)
        is_async=True,
        args={
            "docname": doc.name,
            "telegram_user_id": user_info.get("telegram_user_id")
        }
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
