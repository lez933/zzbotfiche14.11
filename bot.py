import re
import os
from telegram import Update, Document
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

TOKEN = "8208686892:AAEx1zzR7C4aBBJhcxYsCagMLexzyM6oRk4"

DATA_FILE = "data.txt"

seen_phones = set()
seen_ibans = set()
records = []

# ==========================
# OUTILS EXTRACTION
# ==========================

def extract_phone(line):
    m = re.search(r"\b0[67]\d{8}\b", line)
    return m.group(0) if m else ""

def extract_email(line):
    m = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", line)
    return m.group(0) if m else ""

def extract_birthdate(line):
    dates = re.findall(r"\b\d{2}/\d{2}/\d{4}\b", line)
    return dates[-1] if dates else ""

def extract_iban(line):
    m = re.search(r"\bFR\d{25}\b", line)
    return m.group(0) if m else ""

def extract_bic(line):
    m = re.search(r"\b[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?\b", line)
    return m.group(0)[:6] if m else ""

def extract_name(line):
    parts = line.split("|")
    for i in range(len(parts)-2):
        if parts[i] == "N":
            nom = parts[i+1].strip()
            prenom = parts[i+2].strip()
            if nom.isalpha():
                return nom.upper(), prenom.title()
    return "", ""

def extract_address(line):
    m = re.search(r"\|\d{1,4}\s.+?\|\d{5}\b", line)
    return m.group(0).replace("|", " ").strip() if m else ""

# ==========================
# PARSE LIGNE COMPLETE
# ==========================

def parse_line(line):
    phone = extract_phone(line)
    email = extract_email(line)
    birth = extract_birthdate(line)
    iban = extract_iban(line)
    bic = extract_bic(line)
    nom, prenom = extract_name(line)
    address = extract_address(line)

    if not phone:
        return None

    return {
        "phone": phone,
        "email": email,
        "birth": birth,
        "iban": iban,
        "bic": bic,
        "nom": nom,
        "prenom": prenom,
        "address": address
    }

# ==========================
# TELEGRAM HANDLERS
# ==========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot prêt.\nEnvoie un fichier .txt ou /num 06XXXXXXXX")

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc: Document = update.message.document
    path = await doc.get_file()
    tmp = "upload.txt"
    await path.download_to_drive(tmp)

    added = 0
    ignored = 0

    with open(tmp, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            rec = parse_line(line)
            if not rec:
                continue

            if rec["phone"] in seen_phones or rec["iban"] in seen_ibans:
                ignored += 1
                continue

            seen_phones.add(rec["phone"])
            if rec["iban"]:
                seen_ibans.add(rec["iban"])

            records.append(rec)
            added += 1

    os.remove(tmp)

    await update.message.reply_text(
        f"✅ Import OK !\n"
        f"➕ {added} ajoutées\n"
        f"🚫 {ignored} doublons ignorés\n"
        f"📊 Total {len(records)}"
    )

async def handle_num(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return

    num = context.args[0]
    for r in records:
        if r["phone"] == num:
            msg = (
                f"📄 Fiche pour {r['nom']} {r['prenom']}\n"
                f"Date de naissance: {r['birth']}\n"
                f"Adresse: {r['address']}\n"
                f"Email: {r['email']}\n"
                f"IBAN: {r['iban']}\n"
                f"BIC: {r['bic']}"
            )
            await update.message.reply_text(msg)
            return

    await update.message.reply_text("❌ Aucune fiche trouvée")

# ==========================
# MAIN
# ==========================

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("num", handle_num))
app.add_handler(MessageHandler(filters.Document.TEXT, handle_file))

print("🤖 Bot lancé")
app.run_polling()
