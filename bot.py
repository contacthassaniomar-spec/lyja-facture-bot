import os
import json
from pathlib import Path
from datetime import date
from decimal import Decimal

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters
)

import db
from pdf_gen import draw_invoice_pdf

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"

def load_config():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

CFG = load_config()

def get_logo_path() -> Path:
    p = CFG.get("pdf", {}).get("logo_path", "assets/logo.png")
    return (BASE_DIR / p).resolve()

def admin_allowed(user_id: int) -> bool:
    if not CFG.get("bot", {}).get("admin_only", False):
        return True
    admin_id = os.getenv("OWNER_TELEGRAM_ID", "")
    return admin_id.isdigit() and int(admin_id) == int(user_id)

def money_to_float(text: str) -> float:
    t = (text or "").strip().replace("€","").replace(" ", "").replace(",", ".")
    return float(Decimal(t))

# ---------------- States ----------------
(
    MENU,
    CLIENT_CHOOSE,
    CLIENT_SEARCH,
    CLIENT_ADD_NAME,
    CLIENT_ADD_ADDR,
    CLIENT_ADD_CITYZIP,
    CLIENT_ADD_SIRET,
    CLIENT_ADD_TVA,
    INV_DESC,
    INV_PRICE,
    INV_CONFIRM,
    INV_FORCE_NUMBER,
    IMPORT_CLIENTS
) = range(13)

# ---------------- Keyboards ----------------
def presets_keyboard():
    presets = CFG["invoice"]["description_presets"]
    rows = [[InlineKeyboardButton(p, callback_data=f"PRESET::{p}")] for p in presets]
    rows.append([InlineKeyboardButton("✍️ Saisie manuelle", callback_data="PRESET::MANUAL")])
    return InlineKeyboardMarkup(rows)

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧾 Créer une facture", callback_data="MENU::NEW_INV")],
        [InlineKeyboardButton("👥 Clients (liste)", callback_data="MENU::LIST_CLIENTS")],
        [InlineKeyboardButton("➕ Ajouter un client", callback_data="MENU::ADD_CLIENT")],
        [InlineKeyboardButton("📥 Import clients", callback_data="MENU::IMPORT_CLIENTS")]
    ])

def client_to_btn(c):
    label = c["name"]
    if c.get("city"):
        label += f" — {c['city']}"
    return InlineKeyboardButton(label[:60], callback_data=f"CLIENT::{c['id']}")

# ---------------- Handlers ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_allowed(update.effective_user.id):
        await update.message.reply_text("Accès refusé.")
        return ConversationHandler.END

    db.init_db()
    await update.message.reply_text("Bienvenue 👋\nChoisis une action :", reply_markup=main_menu_keyboard())
    return MENU

async def menu_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    action = q.data

    if action == "MENU::NEW_INV":
        context.user_data.clear()
        await q.edit_message_text("Pour créer une facture, choisis d'abord le client :", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔎 Rechercher", callback_data="CLIENTMODE::SEARCH")],
            [InlineKeyboardButton("➕ Ajouter un client", callback_data="CLIENTMODE::ADD")],
            [InlineKeyboardButton("⬅️ Menu", callback_data="BACK::MENU")]
        ]))
        return CLIENT_CHOOSE

    if action == "MENU::LIST_CLIENTS":
        clients = db.list_clients(200)
        if not clients:
            await q.edit_message_text("Aucun client enregistré.", reply_markup=main_menu_keyboard())
            return MENU
        kb = [[client_to_btn(c)] for c in clients[:40]]
        kb.append([InlineKeyboardButton("🔎 Rechercher", callback_data="CLIENTMODE::SEARCH")])
        kb.append([InlineKeyboardButton("⬅️ Menu", callback_data="BACK::MENU")])
        await q.edit_message_text("Clients (choisis-en un) :", reply_markup=InlineKeyboardMarkup(kb))
        return CLIENT_CHOOSE

    if action == "MENU::ADD_CLIENT":
        await q.edit_message_text("Nom du client ? (ex: HOCIPHONE)")
        return CLIENT_ADD_NAME

    if action == "MENU::IMPORT_CLIENTS":
        await q.edit_message_text(
            "📥 Import clients\n\n"
            "Colle tes clients (1 par ligne) au format :\n"
            "NOM | ADRESSE | CP | VILLE | SIRET | TVA\n\n"
            "Si TVA n’existe pas, mets '-'.\n\n"
            "Exemple :\n"
            "HOCIPHONE | 160 chemin... | 13015 | Marseille | 4097... | -\n\n"
            "➡️ Colle maintenant ton bloc."
        )
        return IMPORT_CLIENTS

    await q.edit_message_text("Menu :", reply_markup=main_menu_keyboard())
    return MENU

async def back_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("Menu :", reply_markup=main_menu_keyboard())
    return MENU

async def client_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "CLIENTMODE::SEARCH":
        await q.edit_message_text("Tape le nom / email / tel du client :")
        return CLIENT_SEARCH

    if q.data == "CLIENTMODE::ADD":
        await q.edit_message_text("Nom du client ?")
        return CLIENT_ADD_NAME

    return CLIENT_CHOOSE

async def client_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = (update.message.text or "").strip()
    results = db.search_clients(q, 20)
    if not results:
        await update.message.reply_text("Aucun résultat. Réessaie.")
        return CLIENT_SEARCH

    kb = [[client_to_btn(c)] for c in results]
    kb.append([InlineKeyboardButton("⬅️ Menu", callback_data="BACK::MENU")])
    await update.message.reply_text("Résultats :", reply_markup=InlineKeyboardMarkup(kb))
    return CLIENT_CHOOSE

async def client_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cid = int(q.data.split("::")[1])
    client = db.get_client(cid)
    context.user_data["client_id"] = cid
    context.user_data["client"] = client

    await q.edit_message_text("Choisis une description (ou saisie manuelle) :", reply_markup=presets_keyboard())
    return INV_DESC

async def add_client_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = (update.message.text or "").strip()
    if not name:
        await update.message.reply_text("Nom vide. Réessaie.")
        return CLIENT_ADD_NAME
    context.user_data["new_client"] = {"name": name}
    await update.message.reply_text("Adresse ligne 1 ?")
    return CLIENT_ADD_ADDR

async def add_client_addr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_client"]["address1"] = (update.message.text or "").strip()
    await update.message.reply_text("Code postal + Ville ? (ex: 13015 Marseille)")
    return CLIENT_ADD_CITYZIP

async def add_client_cityzip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.message.text or "").strip()
    parts = txt.split()
    context.user_data["new_client"]["zip"] = parts[0] if parts else ""
    context.user_data["new_client"]["city"] = " ".join(parts[1:]) if len(parts) > 1 else ""
    await update.message.reply_text("SIRET du client ? (ou '-' si rien)")
    return CLIENT_ADD_SIRET

async def add_client_siret(update: Update, context: ContextTypes.DEFAULT_TYPE):
    siret = (update.message.text or "").strip()
    if siret == "-":
        siret = ""
    context.user_data["new_client"]["siret"] = siret
    await update.message.reply_text("TVA du client ? (ou '-' si rien)")
    return CLIENT_ADD_TVA

async def add_client_tva(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tva = (update.message.text or "").strip()
    if tva == "-":
        tva = ""
    nc = context.user_data["new_client"]
    cid = db.add_client(
        name=nc["name"],
        address1=nc.get("address1",""),
        zip_code=nc.get("zip",""),
        city=nc.get("city",""),
        country="France",
        siret=nc.get("siret",""),
        tva=tva
    )
    client = db.get_client(cid)
    db.client_folder(client)  # crée le dossier client
    context.user_data["client_id"] = cid
    context.user_data["client"] = client

    await update.message.reply_text(f"✅ Client ajouté: {client['name']}\nChoisis une description :", reply_markup=presets_keyboard())
    return INV_DESC

async def desc_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, val = q.data.split("::", 1)

    if val == "MANUAL":
        await q.edit_message_text("Tape la description (ex: Prestation de services)")
        return INV_DESC

    context.user_data["description"] = val
    await q.edit_message_text("Montant à facturer (TTC – TVA non applicable)")
    return INV_PRICE

async def desc_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    desc = (update.message.text or "").strip()
    if not desc:
        await update.message.reply_text("Description vide. Réessaie.")
        return INV_DESC
    context.user_data["description"] = desc
    await update.message.reply_text("Montant à facturer (TTC – TVA non applicable)")
    return INV_PRICE

async def price_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = money_to_float(update.message.text)
    except:
        await update.message.reply_text("Prix invalide. Exemple: 738 ou 738,00")
        return INV_PRICE

    context.user_data["unit_price"] = price
    context.user_data["qty"] = float(CFG["invoice"]["qty_default"])
    context.user_data["unit"] = CFG["invoice"]["unit_default"]
    context.user_data["tax_rate"] = 0.0

    prefix = CFG["invoice"]["number_prefix"]
    use_year = bool(CFG["invoice"].get("use_year", True))
    number = db.next_invoice_number(prefix, date.today(), use_year=use_year)
    context.user_data["number"] = number

    client = context.user_data["client"]
    msg = (
        f"📌 Récap:\n"
        f"Client: {client['name']}\n"
        f"Description: {context.user_data['description']}\n"
        f"Prix HT: {price:.2f} €\n"
        f"N°: {number}\n\n"
        f"✅ Confirmer ? (ou modifier le numéro)"
    ).replace(".", ",")

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Générer PDF", callback_data="INV::CONFIRM")],
        [InlineKeyboardButton("✏️ Modifier numéro", callback_data="INV::FORCE_NUMBER")],
        [InlineKeyboardButton("⬅️ Menu", callback_data="BACK::MENU")]
    ])
    await update.message.reply_text(msg, reply_markup=kb)
    return INV_CONFIRM

async def inv_confirm_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "INV::FORCE_NUMBER":
        await q.edit_message_text(
            "Tape le numéro:\n"
            "- soit juste le chiffre (ex: 31)\n"
            "- soit le format complet (ex: FACTURE-2026-031)\n"
        )
        return INV_FORCE_NUMBER

    if q.data != "INV::CONFIRM":
        return INV_CONFIRM

    client = context.user_data["client"]
    company = CFG["company"]

    number = context.user_data["number"]
    issue = date.today()
    due = CFG["invoice"]["due_default"]
    op = CFG["invoice"]["operation_type_default"]
    desc = context.user_data["description"]
    qty = context.user_data["qty"]
    unit = context.user_data["unit"]
    unit_price = context.user_data["unit_price"]
    tax_rate = context.user_data["tax_rate"]

    total_ht = float(qty) * float(unit_price)
    total_tva = 0.0
    total_ttc = total_ht

    folder = db.client_folder(client)
    pdf_path = folder / f"{number}.pdf"

    invoice_doc = {
        "title": f"{CFG['invoice']['number_prefix']} - {number}",
        "number": number,
        "issue_date": issue,
        "due": due,
        "operation_type": op,
        "description": desc,
        "qty": qty,
        "unit": unit,
        "unit_price": unit_price,
        "tax_rate": tax_rate,
        "total_ht": total_ht,
        "total_tva": total_tva,
        "total_ttc": total_ttc
    }

    logo = get_logo_path()
    draw_invoice_pdf(pdf_path, company, client, invoice_doc, logo)

    db.save_invoice(
        client_id=client["id"],
        number=number,
        issue_date=issue,
        due=due,
        operation_type=op,
        description=desc,
        qty=qty,
        unit=unit,
        unit_price=unit_price,
        tax_rate=tax_rate,
        total_ht=total_ht,
        total_tva=total_tva,
        total_ttc=total_ttc,
        pdf_path=str(pdf_path)
    )

    await q.edit_message_text("✅ Facture générée. Envoi du PDF…")
    await q.message.reply_document(document=InputFile(str(pdf_path)), filename=f"{number}.pdf")
    await q.message.reply_text("Menu :", reply_markup=main_menu_keyboard())
    return MENU

async def force_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.message.text or "").strip()
    prefix = CFG["invoice"]["number_prefix"]
    year = date.today().year

    if txt.upper().startswith(prefix.upper()):
        number = txt
    else:
        try:
            n = int(txt)
            number = f"{prefix}-{year}-{n:03d}"
        except:
            await update.message.reply_text("Numéro invalide. Exemple: 31 ou FACTURE-2026-031")
            return INV_FORCE_NUMBER

    context.user_data["number"] = number
    await update.message.reply_text(f"✅ Numéro mis à jour: {number}\nClique sur “Générer PDF” dans le récap.")
    return INV_CONFIRM

async def import_clients(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.message.text or "").strip()
    lines = [l.strip() for l in txt.splitlines() if l.strip()]
    ok, bad = 0, 0

    for line in lines:
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 4:
            bad += 1
            continue

        name = parts[0]
        address1 = parts[1]
        zip_code = parts[2]
        city = parts[3]
        siret = parts[4] if len(parts) > 4 else ""
        tva = parts[5] if len(parts) > 5 else ""

        if siret == "-": siret = ""
        if tva == "-": tva = ""

        cid = db.add_client(
            name=name,
            address1=address1,
            zip_code=zip_code,
            city=city,
            country="France",
            siret=siret,
            tva=tva
        )
        client = db.get_client(cid)
        db.client_folder(client)  # crée le dossier client
        ok += 1

    await update.message.reply_text(
        f"✅ Import terminé\nAjoutés: {ok}\nIgnorés: {bad}\n\nMenu :",
        reply_markup=main_menu_keyboard()
    )
    return MENU

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Commande inconnue. Tape /start")

def main():
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN manquant (Railway Variables).")

    db.init_db()

    app = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [
                CallbackQueryHandler(menu_click, pattern=r"^MENU::"),
                CallbackQueryHandler(back_menu, pattern=r"^BACK::MENU$"),
            ],
            CLIENT_CHOOSE: [
                CallbackQueryHandler(client_mode, pattern=r"^CLIENTMODE::"),
                CallbackQueryHandler(client_select, pattern=r"^CLIENT::"),
                CallbackQueryHandler(back_menu, pattern=r"^BACK::MENU$"),
            ],
            CLIENT_SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_search)],
            CLIENT_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_client_name)],
            CLIENT_ADD_ADDR: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_client_addr)],
            CLIENT_ADD_CITYZIP: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_client_cityzip)],
            CLIENT_ADD_SIRET: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_client_siret)],
            CLIENT_ADD_TVA: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_client_tva)],
            INV_DESC: [
                CallbackQueryHandler(desc_pick, pattern=r"^PRESET::"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, desc_manual),
            ],
            INV_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, price_step)],
            INV_CONFIRM: [
                CallbackQueryHandler(inv_confirm_click, pattern=r"^INV::"),
                CallbackQueryHandler(back_menu, pattern=r"^BACK::MENU$"),
            ],
            INV_FORCE_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, force_number)],
            IMPORT_CLIENTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, import_clients)],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True
    )

    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.COMMAND, unknown))
    app.run_polling()

if __name__ == "__main__":
    main()
