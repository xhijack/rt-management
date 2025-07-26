import requests
import frappe

import requests
import frappe
from frappe.utils import formatdate

from frappe.utils.pdf import get_pdf

def on_submit(doc, method):
    """
    Hook Sales Invoice on_submit: generate PDF dan kirim ke Telegram.
    """
    # 1. Ambil data Telegram User
    user_info = get_telegram_user_by_customer(doc.customer)
    if not user_info:
        return

    # 2. Ambil token bot
    bot_name = frappe.get_all("Telegram Bot", pluck="name")[0]
    token = frappe.get_doc("Telegram Bot", bot_name).get_password("api_token")

    # 3. Render HTML & konversi ke PDF
    html = frappe.get_print("Sales Invoice", doc.name,
                            print_format="Standard", doc=doc, no_letterhead=1)
    pdf_bytes = get_pdf(html)

    # 4. Siapkan payload multipart
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    files = {
        "document": (
            f"{doc.name}.pdf",
            pdf_bytes,
            "application/pdf"
        )
    }
    data = {
        "chat_id": user_info.get("telegram_user_id"),
        "caption": (
            f"Assalamualaikum Bapak/Ibu {doc.customer_name},\n"
            f"Berikut adalah tagihan Anda bulan ini:\n"
            f"🔔 *No. Inv {doc.name}* sebesar "
            f"Rp {doc.grand_total:,.2f}\n"
        ),
        "parse_mode": "Markdown"
    }

    # 5. Kirim PDF
    requests.post(url, data=data, files=files)


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
