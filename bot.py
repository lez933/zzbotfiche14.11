import re
import sqlite3
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = "8208686892:AAEx1zzR7C4aBBJhcxYsCagMLexzyM6oRk4"
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

# ================== PARSING ==================
def parse_line(line: str):
    parts = line.strip().split("|")

    if len(parts) < 8:
        return None

    tel = parts[0]
    nom = parts[8] if len(parts) > 8 else ""
    prenom = parts[9] if len(parts) > 9 else ""
    email = next((p for p in parts if "@" in p), "")
    naissance = next((p for p in parts if re.match(r"\d{2}/\d{2}/\d{4}", p)), "")
    iban = next((p for p in parts if p.startswith("FR")), "")
    bic = next((p for p in parts if re.match(r"[A-Z]{6,11}", p)), "")[:6]
    adresse = " ".join(parts[10:14]) if len(parts) > 14 else ""

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

    tel = context.args[0]

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
