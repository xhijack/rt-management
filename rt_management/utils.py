import frappe

@frappe.whitelist()
def get_house_filter_by_customer(customer):
    return frappe.get_all(
        "Customer House",
        filters={"parent": customer},
        pluck="unit"
    )
