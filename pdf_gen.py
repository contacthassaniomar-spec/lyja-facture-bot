from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.colors import black, HexColor
from pathlib import Path

def draw_invoice_pdf(pdf_path, company, client, invoice, logo_path=None):
    pdf_path = Path(pdf_path)
    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    width, height = A4

    # Bande latérale
    c.setFillColor(HexColor("#f2f2f2"))
    c.rect(0, 0, 35 * mm, height, fill=1, stroke=0)

    # Logo
    if logo_path and Path(logo_path).exists():
        c.drawImage(str(logo_path), 10 * mm, height - 40 * mm, width=25 * mm, preserveAspectRatio=True)

    # Titre
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50 * mm, height - 30 * mm, "FACTURE")

    # Infos facture
    c.setFont("Helvetica", 10)
    y = height - 45 * mm
    c.drawString(50 * mm, y, f"Numéro : {invoice['number']}")
    y -= 6 * mm
    c.drawString(50 * mm, y, f"Date : {invoice['issue_date'].strftime('%d/%m/%Y')}")
    y -= 6 * mm
    c.drawString(50 * mm, y, f"Échéance : {invoice['due']}")
    y -= 6 * mm
    c.drawString(50 * mm, y, f"Type d’opération : {invoice['operation_type']}")

    # Société
    y -= 15 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50 * mm, y, company["name"])
    c.setFont("Helvetica", 10)
    y -= 5 * mm
    c.drawString(50 * mm, y, company["address"])
    y -= 5 * mm
    c.drawString(50 * mm, y, f"{company['zip']} {company['city']}")
    y -= 5 * mm
    c.drawString(50 * mm, y, f"SIRET {company['siret']}")

    # Client
    y -= 15 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50 * mm, y, client["name"])
    c.setFont("Helvetica", 10)
    y -= 5 * mm
    c.drawString(50 * mm, y, client["address1"])
    y -= 5 * mm
    c.drawString(50 * mm, y, f"{client['zip']} {client['city']}")
    if client.get("siret"):
        y -= 5 * mm
        c.drawString(50 * mm, y, f"SIRET {client['siret']}")

    # Description
    y -= 15 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50 * mm, y, "Description")
    y -= 6 * mm
    c.setFont("Helvetica", 10)
    c.drawString(50 * mm, y, invoice["description"])

    # Totaux
    y -= 20 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50 * mm, y, f"Total HT : {invoice['total_ht']:.2f} €")

    c.showPage()
    c.save()
