from __future__ import annotations
import os
from typing import Dict, Any
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Table, TableStyle
from reportlab.lib.utils import ImageReader

def eur(x: float) -> str:
    s = f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", " ")
    return f"{s} €"

def build_invoice_pdf(out_path: str, cfg: Dict[str, Any], invoice: Dict[str, Any], seller: Dict[str, Any], client: Dict[str, Any]) -> str:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    c = Canvas(out_path, pagesize=A4)
    w, h = A4

    left = 20 * mm
    right = w - 20 * mm
    top = h - 20 * mm
    y = top

    # Logo (optionnel)
    logo_path = (cfg.get("branding", {}) or {}).get("logo_path")
    if logo_path and os.path.exists(logo_path):
        try:
            img = ImageReader(logo_path)
            c.drawImage(img, left, y - 22*mm, width=32*mm, height=22*mm, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass

    # Titre
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(right, y - 4*mm, f"FACTURE - {invoice['number']}")

    c.setFont("Helvetica", 8)
    c.drawRightString(right, y - 10*mm, f"Date de facturation: {invoice['issue_date']}")
    c.drawRightString(right, y - 14*mm, f"Échéance: {invoice['due_text']}")
    c.drawRightString(right, y - 18*mm, f"Type d'opération: {invoice['operation_type']}")

    # Bloc vendeur (gauche)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y - 40*mm, seller.get("brand_name",""))
    c.setFont("Helvetica", 9)
    lines = [
        seller.get("legal_name",""),
        *(seller.get("address_lines") or []),
        seller.get("phone",""),
        seller.get("email",""),
    ]
    yy = y - 46*mm
    for ln in [l for l in lines if l]:
        c.drawString(left, yy, ln)
        yy -= 5*mm

    # ✅ SIRET + TVA sous tes infos (vendeur)
    c.setFont("Helvetica", 8)
    if seller.get("siret"):
        c.drawString(left, yy, f"Numéro de SIRET {seller.get('siret')}")
        yy -= 4.5*mm
    if seller.get("vat_note"):
        c.drawString(left, yy, seller.get("vat_note"))
        yy -= 4.5*mm

    # Bloc client (droite)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(w/2 + 10*mm, y - 48*mm, (client.get("name") or "").upper())
    c.setFont("Helvetica", 9)
    c.drawString(w/2 + 10*mm, y - 54*mm, client.get("address1") or "")
    c.drawString(w/2 + 10*mm, y - 59*mm, f"{client.get('zip','') or ''} {client.get('city','') or ''}".strip())

    # Tableau
    table_top = y - 105*mm
    data = [
        ["No.", "Description", "Date", "Qté", "Unité", "Prix unitaire", "TVA", "Montant"],
        [
            "1",
            invoice["description"],
            invoice["issue_date"],
            f"{invoice['qty']:.2f}".replace(".", ","),
            invoice["unit"],
            eur(invoice["unit_price"]),
            f"{invoice['vat_rate']:.2f} %".replace(".", ","),
            eur(invoice["total_ht"]),
        ],
    ]

    col_widths = [10*mm, 64*mm, 20*mm, 12*mm, 14*mm, 24*mm, 14*mm, 22*mm]
    t = Table(data, colWidths=col_widths, rowHeights=[8*mm, 8*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#E6E6E6")),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 8),
        ("ALIGN", (0,0), (0,-1), "CENTER"),
        ("ALIGN", (2,1), (-1,-1), "CENTER"),
        ("ALIGN", (1,1), (1,1), "LEFT"),
        ("GRID", (0,0), (-1,-1), 0.25, colors.HexColor("#BDBDBD")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    tw, th = t.wrapOn(c, right-left, h)
    t.drawOn(c, left, table_top - th)

    # Totaux
    totals_y = table_top - th - 12*mm
    c.setFont("Helvetica", 8.5)
    c.drawRightString(right - 24*mm, totals_y, "Total HT")
    c.drawRightString(right, totals_y, eur(invoice["total_ht"]))
    totals_y -= 5*mm
    c.drawRightString(right - 24*mm, totals_y, f"TVA {invoice['vat_rate']:.2f} %".replace(".", ","))
    c.drawRightString(right, totals_y, eur(invoice["total_vat"]))
    totals_y -= 6*mm
    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(right - 24*mm, totals_y, "Total TTC")
    c.drawRightString(right, totals_y, eur(invoice["total_ttc"]))

    # Footer
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(w/2, 20*mm, seller.get("brand_name",""))
    c.setFont("Helvetica", 7.5)
    if seller.get("footer_line",""):
        c.drawCentredString(w/2, 16*mm, seller.get("footer_line",""))

    c.showPage()
    c.save()
    return out_path
