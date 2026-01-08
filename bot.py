import os
import re
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ================= CONFIG =================
TOKEN = "8208686892:AAEx1zzR7C4aBBJhcxYsCagMLexzyM6oRk4"
DB_FILE = "db.json"

# ================= BASE =================
if os.path.exists(DB_FILE):
    with open(DB_FILE, "r", encoding="utf-8") as f:
        db = json.load(f)
else:
    db = {}

# ================= INDEX ANTI DOUBLON =================
index_phone = set()
index_iban = set()
index_email = set()

def rebuild_index():
    index_phone.clear()
    index_iban.clear()
    index_email.clear()

    for num, fiche in db.items():
        index_phone.add(num)

        m = re.search(r"IBAN:\s*(\S+)", fiche)
        if m:
            index_iban.add(m.group(1))

        m = re.search(r"Email:\s*(\S+)", fiche)
        if m:
            index_email.add(m.group(1).lower())

rebuild_index()

def save_db():
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

# ================= OUTILS =================
def normalize_phone(p):
    return re.sub(r"\D", "", p)

def extract_bic(line):
    m = re.search(r"\b([A-Z]{6})[A-Z0-9]{2,5}\b", line)
    return m.group(1) if m else ""

def extract_iban(line):
    m = re.search(r"\bFR\d{25}\b", line)
    return m.group(0) if m else ""

def extract_email(line):
    m = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", line, re.I)
    return m.group(0).lower() if m else ""

def extract_name(line):
    parts = line.split("|")
    nom = prenom = ""
    for i in range(len(parts) - 1):
        if parts[i].isupper() and parts[i+1].istitle():
            nom = parts[i]
            prenom = parts[i+1]
            break
    return nom, prenom

def extract_birth(line):
    dates = re.findall(r"\b\d{2}/\d{2}/\d{4}\b", line)
    return dates[-1] if dates else ""

def extract_address(line):
    parts = line.split("|")
    for p in parts:
        if "RUE" in p.upper() or "AV" in p.upper():
            return p.strip()
    return ""

# ================= IMPORT TXT =================
def import_txt(text):
    added = 0
    duplicate = 0

    for line in text.splitlines():
        if "|" not in line:
            continue

        phone = normalize_phone(line.split("|")[0])
        if not phone:
            continue

        iban = extract_iban(line)
        email = extract_email(line)

        # ⛔ ANTI DOUBLON
        if (
            phone in index_phone or
            (iban and iban in index_iban) or
            (email and email in index_email)
        ):
            duplicate += 1
            continue

        nom, prenom = extract_name(line)
        naissance = extract_birth(line)
        adresse = extract_address(line)
        bic = extract_bic(line)

        fiche = (
            f"Fiche pour {nom} {prenom}\n"
            f"Date de naissance: {naissance}\n"
            f"Adresse: {adresse}\n"
            f"Email: {email}\n"
            f"IBAN: {iban}\n"
            f"BIC: {bic}\n"
        )

        db[phone] = fiche
        index_phone.add(phone)
        if iban:
            index_iban.add(iban)
        if email:
            index_email.add(email)

        added += 1

    if added:
        save_db()

    return added, duplicate

# ================= COMMANDES =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot prêt.\nEnvoie un fichier .txt ou /stat")

async def stat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"📊 Total fiches : {len(db)}")

async def num(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return

    phone = normalize_phone(context.args[0])
    fiche = db.get(phone)

    if fiche:
        await update.message.reply_text(fiche)
    else:
        await update.message.reply_text(f"Aucune fiche pour {phone}")

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    file = await doc.get_file()
    content = await file.download_as_bytearray()
    text = content.decode("utf-8", errors="ignore")

    a, d = import_txt(text)

    await update.message.reply_text(
        f"✅ Import OK !\n"
        f"+{a} ajoutées\n"
        f"⛔ {d} doublons ignorés\n"
        f"📊 Total {len(db)}"
    )

# ================= MAIN =================
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stat", stat))
    app.add_handler(CommandHandler("num", num))
    app.add_handler(MessageHandler(filters.Document.TEXT, handle_file))

    print("Bot lancé...")
    app.run_polling()

if __name__ == "__main__":
    main()

