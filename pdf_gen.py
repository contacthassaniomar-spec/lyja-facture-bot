from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor, black
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from datetime import date, datetime
import os

PURPLE = HexColor("#6A1B9A")
LIGHT_GREY = HexColor("#F5F5F5")


def safe(d, *keys, default=""):
    """Retourne la première clé trouvée (évite KeyError)."""
    if not isinstance(d, dict):
        return default
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return str(d[k])
    return default


def fmt_date(v) -> str:
    """Formate une date en jj/mm/aaaa."""
    if isinstance(v, (date, datetime)):
        return v.strftime("%d/%m/%Y")
    s = str(v) if v is not None else ""
    # si ISO 2026-02-26
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
        except Exception:
            return s
    return s


def eur(v) -> str:
    """Format euros FR: 1 234,56 €"""
    try:
        x = float(v or 0)
    except Exception:
        x = 0.0
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", " ") + " €"


def draw_invoice_pdf(path, company, client, invoice, logo_path=None):
    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4

    # Bande verticale gauche
    c.setFillColor(PURPLE)
    c.rect(0, 0, 18 * mm, h, stroke=0, fill=1)

    # Logo (sécurisé)
    if logo_path:
        try:
            logo_path = str(logo_path)
        except Exception:
            pass

    if logo_path and os.path.exists(logo_path):
        try:
            c.drawImage(
                logo_path,
                25 * mm,
                h - 40 * mm,
                width=40 * mm,
                height=18 * mm,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass

    # Titre
    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(black)
    c.drawRightString(w - 20 * mm, h - 25 * mm, "FACTURE")

    c.setFont("Helvetica", 9)
    c.drawRightString(w - 20 * mm, h - 32 * mm, f"N° {safe(invoice,'number',default='')}")

    # Bloc entreprise
    y = h - 60 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(25 * mm, y, safe(company, "brand", "legal_name", "nom"))

    c.setFont("Helvetica", 9)
    c.drawString(25 * mm, y - 5 * mm, safe(company, "address1", "adresse", "address"))
    c.drawString(25 * mm, y - 10 * mm, f"{safe(company,'zip','zip_code','code_postal','code postal')} {safe(company,'city','ville')}".strip())
    c.drawString(25 * mm, y - 15 * mm, safe(company, "country", "pays", default="France"))

    phone = safe(company, "phone", "tel", "telephone")
    if phone:
        c.drawString(25 * mm, y - 20 * mm, f"Tél : {phone}")

    email = safe(company, "email")
    if email:
        c.drawString(25 * mm, y - 25 * mm, email)

    siret = safe(company, "siret")
    if siret:
        c.drawString(25 * mm, y - 30 * mm, f"SIRET : {siret}")

    # Bloc client
    y2 = y - 45 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(25 * mm, y2, "Facturé à :")

    c.setFont("Helvetica", 9)
    c.drawString(25 * mm, y2 - 5 * mm, safe(client, "name", "nom", default="Client"))
    c.drawString(25 * mm, y2 - 10 * mm, safe(client, "address1", "adresse", "address"))
    c.drawString(
        25 * mm,
        y2 - 15 * mm,
        f"{safe(client,'zip','zip_code','code_postal','code postal')} {safe(client,'city','ville')}".strip(),
    )

    csiret = safe(client, "siret")
    if csiret:
        c.drawString(25 * mm, y2 - 20 * mm, f"SIRET : {csiret}")

    # Infos facture (à droite)
    info_y = y2
    c.drawRightString(w - 20 * mm, info_y, f"Date : {fmt_date(invoice.get('issue_date'))}")
    c.drawRightString(w - 20 * mm, info_y - 5 * mm, f"Échéance : {safe(invoice,'due',default='')}")
    c.drawRightString(w - 20 * mm, info_y - 10 * mm, safe(invoice, "operation_type", default=""))

    # Tableau
    table_y = y2 - 40 * mm
    c.setFillColor(LIGHT_GREY)
    c.rect(25 * mm, table_y, w - 45 * mm, 10 * mm, fill=1, stroke=0)

    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(27 * mm, table_y + 3 * mm, "Description")
    c.drawRightString(w - 95 * mm, table_y + 3 * mm, "Qté")
    c.drawRightString(w - 65 * mm, table_y + 3 * mm, "PU")
    c.drawRightString(w - 40 * mm, table_y + 3 * mm, "Montant")

    # Ligne
    row_y = table_y - 8 * mm
    c.setFont("Helvetica", 9)

    desc = safe(invoice, "description", default="")
    qty = safe(invoice, "qty", default="1")
    unit_price = invoice.get("unit_price", 0)
    total_ttc = invoice.get("total_ttc", 0)

    c.drawString(27 * mm, row_y, desc)
    c.drawRightString(w - 95 * mm, row_y, str(qty))
    c.drawRightString(w - 65 * mm, row_y, eur(unit_price))
    c.drawRightString(w - 40 * mm, row_y, eur(total_ttc))

    # Totaux
    total_y = row_y - 20 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(w - 40 * mm, total_y, f"TOTAL TTC : {eur(total_ttc)}")

    # TVA notice
    vat_notice = safe(company, "vat_notice", default="")
    if vat_notice:
        c.setFont("Helvetica", 8)
        c.drawString(25 * mm, 25 * mm, vat_notice)

    c.showPage()
    c.save()
