import os
import re
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "8208686892:AAEx1zzR7C4aBBJhcxYsCagMLexzyM6oRk4"

DATA_DIR = "output"
DB_FILE = "database.txt"

# ------------------ UTILS ------------------

def normalize_phone(phone: str) -> str:
    phone = phone.strip().replace(" ", "")
    if phone.startswith("+33"):
        phone = "0" + phone[3:]
    elif phone.startswith("33"):
        phone = "0" + phone[2:]
    return phone

def load_database():
    if not os.path.exists(DB_FILE):
        return {}
    db = {}
    with open(DB_FILE, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("|")
            if len(parts) < 8:
                continue
            phone = normalize_phone(parts[3])
            db[phone] = line.strip()
    return db

def save_database(db: dict):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        for line in db.values():
            f.write(line + "\n")

# ------------------ COMMANDES ------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot fiche prêt.\nCommande : /num 06xxxxxxxx")

async def import_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    file = await doc.get_file()
    content = (await file.download_as_bytearray()).decode("utf-8", errors="ignore")

    db = load_database()
    added = 0
    ignored = 0

    for line in content.splitlines():
        parts = line.strip().split("|")
        if len(parts) < 8:
            continue

        phone = normalize_phone(parts[3])
        if phone in db:
            ignored += 1
            continue

        db[phone] = line.strip()
        added += 1

    save_database(db)

    await update.message.reply_text(
        f"✅ Import OK !\n"
        f"➕ {added} ajoutées\n"
        f"🚫 {ignored} doublons ignorés\n"
        f"📊 Total {len(db)}"
    )

async def search_num(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Utilise : /num 06xxxxxxxx")
        return

    phone = normalize_phone(context.args[0])
    db = load_database()

    if phone not in db:
        await update.message.reply_text("❌ Aucune fiche trouvée")
        return

    parts = db[phone].split("|")

    msg = (
        f"📁 Fiche pour {parts[0]} {parts[1]}\n"
        f"🎂 Date de naissance: {parts[4]}\n"
        f"🏠 Adresse: {parts[5]}\n"
        f"📧 Email: {parts[2]}\n"
        f"🏦 IBAN: {parts[6]}\n"
        f"🏦 BIC: {parts[7]}"
    )

    await update.message.reply_text(msg)

# ------------------ MAIN ------------------

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("num", search_num))
    app.add_handler(CommandHandler("import", import_file))

    print("🤖 Bot lancé")
    app.run_polling()

if __name__ == "__main__":
    main()
