import os
import sqlite3
import io
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')
ALLOWED_USER_ID = 6078258363

conn = sqlite3.connect('fichiers.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS fiches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero TEXT NOT NULL,
        content TEXT NOT NULL
    )
''')
conn.commit()

def parse_fiches(content):
    fiches = content.split('----------------------------------------')
    parsed = []
    for fiche in fiches:
        if not fiche.strip():
            continue
        lines = fiche.strip().split('\n')
        mobile = None
        for line in lines:
            if line.startswith('Telephone mobile'):
                mobile = line.split(':', 1)[1].strip()
                if mobile.startswith('06') or mobile.startswith('07'):
                    break
        if mobile:
            parsed.append((mobile, '\n'.join(lines)))
    return parsed

async def ajouter_fiche(update: Update, context: CallbackContext):
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("Accès refusé.")
        return

    message = update.message
    numero = None
    content = None

    if message.caption and 'Ajoute à' in message.caption:
        numero = message.caption.split('Ajoute à')[-1].strip()

    if message.document:
        file = await message.document.get_file()
        byte_array = await file.download_as_bytearray()
        file_content = io.BytesIO(byte_array).read().decode('utf-8', errors='ignore')
        parsed = parse_fiches(file_content)
        if parsed:
            for num, txt in parsed:
                cursor.execute("INSERT INTO fiches (numero, content) VALUES (?, ?)", (num, txt))
            conn.commit()
            await message.reply_text(f"Ajouté {len(parsed)} fiches.")
            return
        else:
            content = file_content
    elif message.text:
        content = message.text

    if content and numero:
        if not (numero.startswith('06') or numero.startswith('07')):
            await update.message.reply_text("Numéro invalide.")
            return
        cursor.execute("INSERT INTO fiches (numero, content) VALUES (?, ?)", (numero, content))
        conn.commit()
        await message.reply_text(f"Fiche ajoutée pour {numero}.")
    else:
        await update.message.reply_text("Envoie un .txt ou texte avec 'Ajoute à 06...'")

async def num_command(update: Update, context: CallbackContext):
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("Accès refusé.")
        return

    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Utilisation : /num 0612345678 4")
        return
    numero = args[0]
    try:
        qty = int(args[1])
    except:
        await update.message.reply_text("Quantité invalide.")
        return

    cursor.execute("SELECT content FROM fiches WHERE numero = ? ORDER BY id DESC LIMIT ?", (numero, qty))
    fiches = cursor.fetchall()
    if not fiches:
        await update.message.reply_text("Aucune fiche.")
        return
    for f in fiches:
        await update.message.reply_text(f[0])

async def start(update: Update, context: CallbackContext):
    await update.message.reply_text("Bonjour le Z")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("num", num_command))
    app.add_handler(MessageHandler(filters.DOCUMENT | filters.TEXT, ajouter_fiche))
    
    # SANS drop_pending_updates → FONCTIONNE SUR RENDER
    app.run_polling()

if __name__ == '__main__':
    main()
