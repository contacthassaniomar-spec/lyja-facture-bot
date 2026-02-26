from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
import os
from datetime import date

BASE_PATH = "/app/data"
LOGO_PATH = "assets/logo.png"

def draw_invoice_pdf(
    filename,
    company,
    company_address,
    company_siret,
    client,
    client_address,
    invoice_number,
    description,
    amount_ttc,
    tva_rate=0.0
):
    os.makedirs(os.path.dirname(filename), exist_ok=True)

    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4

    # LOGO
    if os.path.exists(LOGO_PATH):
        c.drawImage(LOGO_PATH, 20 * mm, height - 40 * mm, width=40 * mm, preserveAspectRatio=True)

    # TITRE
    c.setFont("Helvetica-Bold", 16)
    c.drawString(120 * mm, height - 30 * mm, f"FACTURE {invoice_number}")

    # SOCIÉTÉ
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, height - 55 * mm, company)
    c.drawString(20 * mm, height - 62 * mm, company_address)
    c.drawString(20 * mm, height - 69 * mm, f"SIRET : {company_siret}")

    # CLIENT
    c.setFont("Helvetica-Bold", 11)
    c.drawString(120 * mm, height - 55 * mm, client)
    c.setFont("Helvetica", 10)
    c.drawString(120 * mm, height - 62 * mm, client_address)

    # DESCRIPTION
    y = height - 100 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y, "Description")
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, y - 10 * mm, description)

    # PRIX
    tva_amount = amount_ttc * tva_rate
    total_ht = amount_ttc - tva_amount

    y -= 40 * mm
    c.drawString(120 * mm, y, f"Total HT : {total_ht:.2f} €")
    c.drawString(120 * mm, y - 10 * mm, f"TVA : {tva_amount:.2f} €")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(120 * mm, y - 22 * mm, f"TOTAL TTC : {amount_ttc:.2f} €")

    # MENTION TVA
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, 20 * mm, "TVA non applicable, art. 293B du CGI")

    c.showPage()
    c.save()
