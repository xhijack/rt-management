import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def add_custom_fields():
    custom_fields = {
        "Sales Invoice Item": [
            dict(
                fieldname="unit",
                label="Unit",
                fieldtype="Link",
                options="House",
                inlistview="1",
                insert_after="item_name",  # atau "qty", sesuaikan
                description="Unit rumah yang terkait dengan item ini"
            )
        ],
        "Customer": [
            dict(
                fieldname="unit",
                label="Units",
                fieldtype="Table",
                options="Customer House",
                insert_after="customer_group",  # atau "qty", sesuaikan
                description="Unit rumah yang terkait pelanggan"
            )
        ]
    }

    create_custom_fields(custom_fields, update=True)

def after_migrate():
    add_custom_fields()