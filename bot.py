import re
import sqlite3
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = "MET_TON_VRAI_TOKEN_ICI"
DB = "fiches.db"

# ================== DATABASE ==================
conn = sqlite3.connect(DB, check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS fiches (
    telephone TEXT PRIMARY KEY,
    nom TEXT,
    prenom TEXT,
    naissance TEXT,
    adresse TEXT,
    email TEXT,
    iban TEXT,
    bic TEXT
)
""")
conn.commit()

# ================== OUTILS ==================
def normalize_phone(tel: str) -> str:
    tel = re.sub(r"\D", "", tel)
    if tel.startswith("33") and len(tel) == 11:
        tel = "0" + tel[2:]
    return tel if tel.startswith("0") and len(tel) == 10 else ""

def extract_date(parts):
    for p in parts:
        if re.match(r"\d{2}/\d{2}/\d{4}", p):
            return p
    return ""

def extract_email(parts):
    for p in parts:
        if "@" in p:
            return p
    return ""

def extract_iban(parts):
    for p in parts:
        if p.startswith("FR") and len(p) > 20:
            return p
    return ""

def extract_bic(parts):
    for p in parts:
        if re.match(r"^[A-Z]{6,11}$", p):
            return p[:6]
    return ""

# ================== PARSING ==================
def parse_line(line: str):
    parts = [p.strip() for p in line.split("|")]

    if len(parts) < 5:
        return None

    tel = normalize_phone(parts[0])
    if not tel:
        return None

    nom = parts[8] if len(parts) > 8 else ""
    prenom = parts[9] if len(parts) > 9 else ""
    email = extract_email(parts)
    naissance = extract_date(parts)
    iban = extract_iban(parts)
    bic = extract_bic(parts)

    adresse_parts = []
    for p in parts:
        if re.search(r"\d+ .*", p):
            adresse_parts.append(p)
    adresse = " ".join(adresse_parts[:2])

    return (tel, nom, prenom, naissance, adresse, email, iban, bic)

# ================== IMPORT ==================
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    file = await doc.get_file()
    content = (await file.download_as_bytearray()).decode("utf-8", errors="ignore")

    added = 0
    ignored = 0

    for line in content.splitlines():
        data = parse_line(line)
        if not data:
            continue

        try:
            cur.execute(
                "INSERT INTO fiches VALUES (?,?,?,?,?,?,?,?)",
                data
            )
            added += 1
        except sqlite3.IntegrityError:
            ignored += 1

    conn.commit()

    total = cur.execute("SELECT COUNT(*) FROM fiches").fetchone()[0]

    await update.message.reply_text(
        f"✅ Import OK !\n"
        f"➕ {added} ajoutées\n"
        f"🚫 {ignored} doublons ignorés\n"
        f"📊 Total {total}"
    )

# ================== /num ==================
async def num(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return

    tel = normalize_phone(context.args[0])
    if not tel:
        await update.message.reply_text("❌ Numéro invalide")
        return

    row = cur.execute(
        "SELECT * FROM fiches WHERE telephone=?",
        (tel,)
    ).fetchone()

    if not row:
        await update.message.reply_text("❌ Aucune fiche trouvée")
        return

    t, nom, prenom, naissance, adresse, email, iban, bic = row

    msg = (
        f"📄 Fiche pour {nom} {prenom}\n"
        f"Date de naissance: {naissance}\n"
        f"Adresse: {adresse}\n"
        f"Email: {email}\n"
        f"IBAN: {iban}\n"
        f"BIC: {bic}"
    )

    await update.message.reply_text(msg)

# ================== START ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot prêt")

# ================== MAIN ==================
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("num", num))
app.add_handler(MessageHandler(filters.Document.ALL, handle_file))

app.run_polling()
