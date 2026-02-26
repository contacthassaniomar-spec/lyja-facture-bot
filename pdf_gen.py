from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from pathlib import Path
import os

def draw_invoice_pdf(pdf_path, company, client, invoice, logo_path):
    pdf_path = Path(pdf_path)
    os.makedirs(pdf_path.parent, exist_ok=True)

    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    width, height = A4

    # LOGO
    if logo_path and Path(logo_path).exists():
        c.drawImage(str(logo_path), 20 * mm, height - 40 * mm, width=40 * mm, preserveAspectRatio=True)

    # TITRE
    c.setFont("Helvetica-Bold", 16)
    c.drawString(120 * mm, height - 30 * mm, f"FACTURE {invoice['number']}")

    # SOCIÉTÉ
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, height - 55 * mm, company["name"])
    c.drawString(20 * mm, height - 62 * mm, company["address"])
    c.drawString(20 * mm, height - 69 * mm, f"SIRET : {company['siret']}")

    # CLIENT
    c.setFont("Helvetica-Bold", 11)
    c.drawString(120 * mm, height - 55 * mm, client["name"])
    c.setFont("Helvetica", 10)
    c.drawString(120 * mm, height - 62 * mm, client["address1"])
    c.drawString(120 * mm, height - 69 * mm, f"{client['zip_code']} {client['city']}")

    # INFOS FACTURE
    y = height - 100 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y, "Description")
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, y - 10 * mm, invoice["description"])

    # TOTAUX
    y -= 40 * mm
    c.drawString(120 * mm, y, f"Montant HT : {invoice['total_ht']:.2f} €")
    c.drawString(120 * mm, y - 10 * mm, "TVA : 0.00 € (art. 293B CGI)")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(120 * mm, y - 22 * mm, f"TOTAL À PAYER : {invoice['total_ttc']:.2f} €")

    # PIED DE PAGE
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, 20 * mm, "TVA non applicable, art. 293B du CGI")

    c.showPage()
    c.save()
