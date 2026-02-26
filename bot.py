from __future__ import annotations
import os, json
from datetime import date
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ConversationHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

import db
from pdf import build_invoice_pdf

(
    MENU,
    CLIENT_CHOOSE,
    CLIENT_SEARCH,
    CLIENT_NEW_NAME,
    CLIENT_NEW_ADDRESS1,
    CLIENT_NEW_ZIPCITY,
    CLIENT_NEW_SIRET,
    INVOICE_DESC,
    INVOICE_AMOUNT,
) = range(9)

def load_config():
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)

def main_menu_kb():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("🧾 Créer une facture")],
         [KeyboardButton("👥 Clients"), KeyboardButton("ℹ️ Mes infos")]],
        resize_keyboard=True
    )

def _safe(t: str) -> str:
    return (t or "").strip()

def _parse_amount(txt: str) -> float:
    t = _safe(txt).replace("€","").replace(" ", "").replace(",", ".")
    return float(t)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bienvenue 👋\nChoisis une action :", reply_markup=main_menu_kb())
    return MENU

async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = _safe(update.message.text)
    if "Créer" in txt:
        return await create_invoice_entry(update, context)
    if "Clients" in txt:
        return await clients_entry(update, context)
    if "Mes infos" in txt:
        return await my_info(update, context)
    await update.message.reply_text("Choisis un bouton 👇", reply_markup=main_menu_kb())
    return MENU

async def my_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = load_config()
    s = cfg["seller"]
    msg = (
        f"*Mes infos (vendeur)*\n"
        f"- Nom: `{s.get('brand_name','')}`\n"
        f"- Responsable: `{s.get('legal_name','')}`\n"
        f"- Adresse: `{', '.join(s.get('address_lines', []))}`\n"
        f"- Tél: `{s.get('phone','')}`\n"
        f"- Email: `{s.get('email','')}`\n"
        f"- SIRET: `{s.get('siret','')}`\n"
        f"- TVA: `{s.get('vat_note','')}`\n"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu_kb())
    return MENU

async def clients_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clients = db.list_clients(limit=8)
    buttons = [[InlineKeyboardButton(f"{c['name']}", callback_data=f"pickclient:{c['id']}")] for c in clients]
    buttons.append([InlineKeyboardButton("🔎 Rechercher", callback_data="searchclient")])
    buttons.append([InlineKeyboardButton("➕ Ajouter un client", callback_data="newclient")])
    await update.message.reply_text("Clients : choisis, recherche, ou ajoute.", reply_markup=InlineKeyboardMarkup(buttons))
    return CLIENT_CHOOSE

async def create_invoice_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clients = db.list_clients(limit=8)
    buttons = [[InlineKeyboardButton(f"{c['name']}", callback_data=f"pickclient:{c['id']}")] for c in clients]
    buttons.append([InlineKeyboardButton("🔎 Rechercher", callback_data="searchclient")])
    buttons.append([InlineKeyboardButton("➕ Ajouter un client", callback_data="newclient")])
    await update.message.reply_text("Pour créer une facture, choisis d’abord le client :", reply_markup=InlineKeyboardMarkup(buttons))
    return CLIENT_CHOOSE

async def client_choose_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data == "searchclient":
        await q.message.reply_text("Tape le nom / email / tel du client :")
        return CLIENT_SEARCH

    if data == "newclient":
        context.user_data["new_client"] = {}
        await q.message.reply_text("Nom du client / entreprise ?")
        return CLIENT_NEW_NAME

    if data.startswith("pickclient:"):
        client_id = int(data.split(":")[1])
        context.user_data["client_id"] = client_id
        client = db.get_client(client_id)
        await q.message.reply_text(f"Client sélectionné ✅: *{client['name']}*\n\nIntitulé / description ?", parse_mode=ParseMode.MARKDOWN)
        return INVOICE_DESC

    return CLIENT_CHOOSE

async def client_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    qtxt = _safe(update.message.text)
    clients = db.list_clients(limit=12, q=qtxt)
    if not clients:
        await update.message.reply_text("Aucun résultat. Réessaie.")
        return CLIENT_SEARCH
    buttons = [[InlineKeyboardButton(f"{c['name']}", callback_data=f"pickclient:{c['id']}")] for c in clients]
    buttons.append([InlineKeyboardButton("➕ Ajouter un client", callback_data="newclient")])
    await update.message.reply_text("Résultats :", reply_markup=InlineKeyboardMarkup(buttons))
    return CLIENT_CHOOSE

async def client_new_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_client"]["name"] = _safe(update.message.text)
    await update.message.reply_text("Adresse ligne 1 ?")
    return CLIENT_NEW_ADDRESS1

async def client_new_address1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_client"]["address1"] = _safe(update.message.text)
    await update.message.reply_text("Code postal + Ville (ex: 13013 Marseille) ?")
    return CLIENT_NEW_ZIPCITY

async def client_new_zipcity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = _safe(update.message.text)
    parts = txt.split(" ", 1)
    context.user_data["new_client"]["zip"] = parts[0] if parts else ""
    context.user_data["new_client"]["city"] = parts[1] if len(parts) > 1 else ""
    await update.message.reply_text("SIRET client ? (sinon envoie '-')")
    return CLIENT_NEW_SIRET

async def client_new_siret(update: Update, context: ContextTypes.DEFAULT_TYPE):
    siret = _safe(update.message.text)
    context.user_data["new_client"]["siret"] = "" if siret == "-" else siret
    context.user_data["new_client"]["country"] = "France"

    cid = db.upsert_client(context.user_data["new_client"])
    context.user_data["client_id"] = cid
    await update.message.reply_text("Client ajouté ✅\n\nIntitulé / description ?")
    return INVOICE_DESC

async def invoice_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["invoice_desc"] = _safe(update.message.text)
    await update.message.reply_text("Montant TTC (€) ?")
    return INVOICE_AMOUNT

async def invoice_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = load_config()
    seller = cfg["seller"]
    inv_cfg = cfg["invoice"]

    amount_ttc = _parse_amount(update.message.text)
    issue = date.today()
    number = db.next_invoice_number(inv_cfg["number_prefix"], issue)

    invoice = {
        "number": number,
        "issue_date": issue.strftime("%d/%m/%Y"),
        "due_text": inv_cfg.get("due_default", "À la réception de la facture"),
        "operation_type": inv_cfg.get("operation_type_default", "Prestation de services"),
        "description": context.user_data["invoice_desc"],
        "qty": float(inv_cfg.get("qty_default", 1)),
        "unit": inv_cfg.get("unit_default", "u"),
        "unit_price": float(amount_ttc),
        "vat_rate": 0.0,
        "total_ht": float(amount_ttc),
        "total_vat": 0.0,
        "total_ttc": float(amount_ttc),
        "currency": inv_cfg.get("currency", "EUR")
    }

    client_id = int(context.user_data["client_id"])
    client = db.get_client(client_id)

    db.create_invoice({**invoice, "issue_date": issue.isoformat(), "client_id": client_id})

    out_dir = os.path.join("data", "pdf")
    os.makedirs(out_dir, exist_ok=True)
    pdf_path = os.path.join(out_dir, f"{number}.pdf")

    build_invoice_pdf(pdf_path, cfg, invoice, seller, client)

    caption = f"🧾 *Facture créée*\n- N°: `{number}`\n- Client: *{client['name']}*\n- Total: *{amount_ttc:.2f} €*"
    await update.message.reply_document(
        document=open(pdf_path, "rb"),
        filename=f"{number}.pdf",
        caption=caption,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_kb()
    )
    return MENU

def build_app() -> Application:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN manquant")
    db.init_db()
    app = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, menu_router)],
            CLIENT_CHOOSE: [CallbackQueryHandler(client_choose_cb)],
            CLIENT_SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_search)],
            CLIENT_NEW_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_new_name)],
            CLIENT_NEW_ADDRESS1: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_new_address1)],
            CLIENT_NEW_ZIPCITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_new_zipcity)],
            CLIENT_NEW_SIRET: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_new_siret)],
            INVOICE_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, invoice_desc)],
            INVOICE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, invoice_amount)],
        },
        fallbacks=[],
        allow_reentry=True
    )
    app.add_handler(conv)
    return app

if __name__ == "__main__":
    app = build_app()
    print("Bot lancé…")
    app.run_polling(close_loop=False)
