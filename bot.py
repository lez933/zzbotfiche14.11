#!/usr/bin/env python3
"""
leZbot — Version FINALE corrigée pour Railway (v20 python-telegram-bot)
- /num et /mot fonctionnent (insensible à la casse)
- Ultra-rapide (base en mémoire)
- Silence sur messages normaux
"""

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

DB_PATH = Path("db.json")
MAX_REPLY = 3900

# Base en mémoire
db: Dict[str, str] = {}

def log(*args):
    print("[leZbot]", *args, flush=True)

def load_db_once() -> Dict[str, str]:
    if DB_PATH.exists():
        try:
            data = json.loads(DB_PATH.read_text(encoding="utf-8"))
            log(f"Base chargée : {len(data)} fiches")
            return data
        except Exception as e:
            log("Erreur chargement DB:", e)
    log("Base vide")
    return {}

def save_db() -> None:
    tmp = DB_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(DB_PATH)

def normalize_fr_phone(raw: str) -> str:
    s = re.sub(r"[^0-9+]", "", raw)
    if s.startswith("+33"): s = "0" + s[3:]
    elif s.startswith("33"): s = "0" + s[2:]
    if len(s) == 9 and s[0] != "0":
        s = "0" + s
    if len(s) == 10 and s.startswith("0"):
        return s
    return ""

def parse_pipe_separated(text: str) -> List[Tuple[str, str]]:
    pairs = []
    for line in text.strip().splitlines():
        if '|' not in line: continue
        fields = line.split('|')
        if len(fields) < 10: continue
        nom, prenom = fields[0].strip(), fields[1].strip()
        date_naiss, adresse, cp, ville = fields[2].strip(), fields[3].strip(), fields[4].strip(), fields[5].strip()
        tel, email, iban, bic = fields[6].strip(), fields[7].strip(), fields[8].strip(), fields[9].strip()
        num = normalize_fr_phone(tel)
        if not num: continue
        fiche = f"Fiche pour {nom} {prenom}\n"
        if date_naiss: fiche += f"Date de naissance: {date_naiss}\n"
        if adresse or cp or ville: fiche += f"Adresse: {adresse} {cp} {ville}\n"
        if email: fiche += f"Email: {email}\n"
        if iban: fiche += f"IBAN: {iban}\n"
        if bic: fiche += f"BIC: {bic}\n"
        pairs.append((num, fiche.strip()))
    return pairs

def import_text_into_db(text: str) -> Tuple[int, int]:
    added = updated = 0
    lines = text.strip().splitlines()
    if len([l for l in lines if l.count('|') >= 9]) > len(lines) * 0.8 and len(lines) > 1:
        log("Format pipe-separated détecté")
        fiche_pairs = parse_pipe_separated(text)
    else:
        # Autres formats (Fiche X, libre) – simplifié mais efficace
        fiche_pairs = []
        # Tu peux réajouter les anciennes fonctions si besoin, mais pipe est ton principal
        # Pour l'instant on se concentre sur pipe pour éviter les bugs
        pass
    
    for num, fiche in fiche_pairs:
        if num in db:
            if fiche != db[num]:
                db[num] = fiche
                updated += 1
        else:
            db[num] = fiche
            added += 1
    
    if added or updated:
        save_db()
    
    return added, updated

# Commandes
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ leZbot prêt !\n/mot ou /num 06... → fiche\nEnvoie .txt → import")

async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 pong")

async def cmd_stat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"📊 {len(db)} fiches")

async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not db:
        await update.message.reply_text("Rien à exporter.")
        return
    lines = [f"===== {num} =====\n{fiche}\n" for num, fiche in sorted(db.items())]
    path = Path("export.txt")
    path.write_text("\n".join(lines), encoding="utf-8")
    await update.message.reply_document(InputFile(path.open("rb"), "export_fiches.txt"))

async def handle_num_mot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    m = re.search(r"^/(?:num|mot)\s*([+\d][\d .-]*)", text, re.IGNORECASE)
    if not m:
        await update.message.reply_text("Utilise /num ou /mot suivi du numéro")
        return
    num = normalize_fr_phone(m.group(1))
    if not num:
        await update.message.reply_text("Numéro invalide")
        return
    fiche = db.get(num)
    if fiche:
        if len(fiche) > MAX_REPLY:
            fiche = fiche[:MAX_REPLY-50] + "\n… (coupée)"
        await update.message.reply_text(f"📇 Fiche {num}:\n\n{fiche}")
    else:
        await update.message.reply_text(f"Aucune fiche pour {num}")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc: return
    await update.message.reply_text("Traitement du fichier…")
    file = await doc.get_file()
    data = await file.download_as_bytearray()
    text = data.decode("utf-8", errors="ignore")
    added, updated = import_text_into_db(text)
    await update.message.reply_text(f"✅ Import OK ! +{added} ~{updated} → Total {len(db)}")

async def handle_plain_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return  # Silence total

if __name__ == "__main__":
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise SystemExit("⚠️ BOT_TOKEN manquant !")

    db.update(load_db_once())

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("ping", cmd_ping))
    app.add_handler(CommandHandler("stat", cmd_stat))
    app.add_handler(CommandHandler("export", cmd_export))

    # Handler pour /num et /mot (insensible à la casse)
    app.add_handler(MessageHandler(filters.Regex(re.compile(r"^/(num|mot)", re.IGNORECASE)), handle_num_mot))

    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_plain_text))

    print("🚀 leZbot lancé – plus de crash !")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
