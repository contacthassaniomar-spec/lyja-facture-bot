from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor, black, grey
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from datetime import datetime
import os


PURPLE = HexColor("#6A1B9A")
LIGHT_GREY = HexColor("#F5F5F5")


def draw_invoice_pdf(path, company, client, inv, logo_path):
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4

    # ===== Bande verticale gauche =====
    c.setFillColor(PURPLE)
    c.rect(0, 0, 15 * mm, height, fill=1, stroke=0)

    # ===== Logo =====
    if logo_path and os.path.exists(logo_path):
        c.drawImage(
            logo_path,
            22 * mm,
            height - 35 * mm,
            width=40 * mm,
            preserveAspectRatio=True,
            mask="auto"
        )

    # ===== Titre =====
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 20)
    c.drawRightString(width - 20 * mm, height - 30 * mm, "FACTURE")

    c.setFont("Helvetica", 10)
    c.drawRightString(
        width - 20 * mm,
        height - 38 * mm,
        f"N° {inv['number']}"
    )

    # ===== Bloc société =====
    y = height - 55 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(22 * mm, y, company["brand"])

    c.setFont("Helvetica", 9)
    lines = [
        company["legal_name"],
        company["address1"],
        f"{company['zip']} {company['city']}",
        company["country"],
        f"Tél : {company['phone']}",
        company["email"],
        f"SIRET : {company['siret']}",
    ]
    for l in lines:
        y -= 4 * mm
        c.drawString(22 * mm, y, l)

    # ===== Bloc client =====
    y -= 8 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(22 * mm, y, "Facturé à")

    c.setFont("Helvetica", 9)
    y -= 4 * mm
    c.drawString(22 * mm, y, client["name"])
    y -= 4 * mm
    c.drawString(22 * mm, y, client["address1"])
    y -= 4 * mm
    c.drawString(22 * mm, y, f"{client['zip_code']} {client['city']}")
    if client.get("siret"):
        y -= 4 * mm
        c.drawString(22 * mm, y, f"SIRET : {client['siret']}")

    # ===== Bloc infos facture =====
    box_x = width - 95 * mm
    box_y = height - 80 * mm
    c.setFillColor(LIGHT_GREY)
    c.rect(box_x, box_y, 75 * mm, 28 * mm, fill=1, stroke=0)

    c.setFillColor(black)
    c.setFont("Helvetica", 9)
    c.drawString(box_x + 5 * mm, box_y + 18 * mm, f"Date : {inv['issue_date'].strftime('%d/%m/%Y')}")
    c.drawString(box_x + 5 * mm, box_y + 12 * mm, f"Échéance : {inv['due']}")
    c.drawString(box_x + 5 * mm, box_y + 6 * mm, f"Opération : {inv['operation_type']}")

    # ===== Tableau =====
    table_y = box_y - 20 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(22 * mm, table_y, "Description")
    c.drawRightString(width - 70 * mm, table_y, "Qté")
    c.drawRightString(width - 45 * mm, table_y, "PU")
    c.drawRightString(width - 20 * mm, table_y, "Montant")

    c.line(22 * mm, table_y - 2 * mm, width - 20 * mm, table_y - 2 * mm)

    table_y -= 8 * mm
    c.setFont("Helvetica", 9)
    c.drawString(22 * mm, table_y, inv["description"])
    c.drawRightString(width - 70 * mm, table_y, str(inv["qty"]))
    c.drawRightString(width - 45 * mm, table_y, f"{inv['unit_price']:.2f} €")
    c.drawRightString(width - 20 * mm, table_y, f"{inv['total_ttc']:.2f} €")

    # ===== Totaux =====
    totals_y = table_y - 20 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(width - 45 * mm, totals_y, "Total TTC")
    c.drawRightString(width - 20 * mm, totals_y, f"{inv['total_ttc']:.2f} €")

    # ===== Mention TVA =====
    c.setFont("Helvetica", 8)
    c.setFillColor(grey)
    c.drawString(
        22 * mm,
        totals_y - 10 * mm,
        company.get("vat_notice", "TVA non applicable, art. 293 B du CGI")
    )

    # ===== Pied de page =====
    c.setFont("Helvetica", 7)
    c.drawCentredString(
        width / 2,
        10 * mm,
        f"{company['brand']} — {company['address1']} {company['zip']} {company['city']} — SIRET {company['siret']}"
    )

    c.showPage()
    c.save()
