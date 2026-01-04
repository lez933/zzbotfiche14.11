#!/usr/bin/env python3
"""
leZbot — Version OPTIMISÉE POUR LA VITESSE
- Chargement unique de la base au démarrage → /num ultra-rapide même avec 10k+ fiches
- Silence total sur les messages texte normaux
- Support pipe-separated, Fiche X, texte libre
"""

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Fix Windows asyncio
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

DB_PATH = Path("db.json")
MAX_REPLY = 3900
PHONE_RE = re.compile(r"(?:\+?33|0)?\s*[1-9](?:[ .-]?\d){8}")

# === BASE DE DONNÉES EN MÉMOIRE (chargée une seule fois) ===
db: Dict[str, str] = {}

def log(*args):
    print("[leZbot]", *args, flush=True)

def load_db_once() -> Dict[str, str]:
    if DB_PATH.exists():
        try:
            data = json.loads(DB_PATH.read_text(encoding="utf-8"))
            log(f"Base chargée : {len(data)} fiches en mémoire")
            return data
        except Exception as e:
            log("Erreur chargement DB:", e)
    log("Nouvelle base vide créée")
    return {}

def save_db() -> None:
    """Sauvegarde sécurisée sur disque"""
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

def split_fiches(text: str) -> List[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]

def index_fiche_block(block: str) -> List[Tuple[str, str]]:
    found = []
    for m in PHONE_RE.finditer(block):
        n = normalize_fr_phone(m.group())
        if n: found.append((n, block))
    seen = set()
    unique = []
    for num, b in found:
        if num not in seen:
            seen.add(num)
            unique.append((num, b))
    return unique

def index_fiches_file(text: str) -> List[Tuple[str, str]]:
    blocks = re.findall(r"(?ms)^Fiche\s+\d+\s*\n.*?(?=^Fiche\s+\d+\s*\n|\Z)", text)
    pairs: List[Tuple[str, str]] = []
    if not blocks: return pairs
    phone_line_re = re.compile(r"^(?:T[ée]l[ée]phone\s*mobile|Mobile|Portable)\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
    for blk in blocks:
        m = phone_line_re.search(blk)
        cand = m.group(1).strip() if m else ""
        if not cand:
            m2 = re.search(r"\b\d{9,14}\b", blk)
            cand = m2.group(0) if m2 else ""
        num = normalize_fr_phone(cand)
        if num:
            pairs.append((num, blk.strip()))
    seen: Dict[str, str] = {}
    for num, blk in pairs:
        seen[num] = blk
    return list(seen.items())

def parse_pipe_separated(text: str) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
    for line in text.strip().splitlines():
        if '|' not in line: continue
        fields = line.split('|')
        if len(fields) < 10: continue
        
        nom = fields[0].strip()
        prenom = fields[1].strip()
        date_naiss = fields[2].strip()
        adresse = fields[3].strip()
        cp = fields[4].strip()
        ville = fields[5].strip()
        tel = fields[6].strip()
        email = fields[7].strip()
        iban = fields[8].strip()
        bic = fields[9].strip()
        
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
    global db
    added = updated = 0
    
    lines = text.strip().splitlines()
    pipe_lines = [l for l in lines if l.count('|') >= 9]
    
    if len(pipe_lines) > len(lines) * 0.8 and len(lines) > 1:
        log("Format pipe-separated détecté")
        fiche_pairs = parse_pipe_separated(text)
    else:
        fiche_pairs = index_fiches_file(text)
        if not fiche_pairs:
            log("Format libre ou blocs séparés")
            fiche_pairs = []
            for block in split_fiches(text):
                pairs = index_fiche_block(block)
                if not pairs:
                    m = re.search(r"\b\d{10}\b", block)
                    if m:
                        n = normalize_fr_phone(m.group())
                        if n: pairs = [(n, block)]
                fiche_pairs.extend(pairs)
    
    for num, fiche in fiche_pairs:
        if num in db:
            if fiche != db[num]:
                db[num] = fiche
                updated += 1
        else:
            db[num] = fiche
            added += 1
    
    if added or updated:
        save_db()  # Sauvegarde seulement si modification
    
    return added, updated

# === Commandes ===

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ leZbot prêt (version rapide !)\n"
        "• Envoie un .txt → import fiches\n"
        "• /num 0600000000 → fiche instantanée\n"
        "• /stat • /export • /ping"
    )

async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 pong")

async def cmd_stat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"📊 {len(db)} fiches en base")

async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not db:
        await update.message.reply_text("Rien à exporter.")
        return
    lines = [f"===== {num} =====\n{fiche}\n" for num, fiche in sorted(db.items())]
    path = Path("export_fiches.txt")
    path.write_text("\n".join(lines), encoding="utf-8")
    await update.message.reply_document(document=InputFile(path.open("rb"), filename="toutes_les_fiches.txt"))

async def handle_num(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    m = re.search(r"/num\s*([+\d][\d .-]*)", text, re.IGNORECASE)
    if not m:
        await update.message.reply_text("Utilise : /num 0600000000")
        return
    num = normalize_fr_phone(m.group(1))
    if not num:
        await update.message.reply_text("Numéro invalide")
        return
    
    fiche = db.get(num)
    if fiche:
        if len(fiche) > MAX_REPLY:
            fiche = fiche[:MAX_REPLY-50] + "\n… (fiche coupée)"
        await update.message.reply_text(f"📇 Fiche {num}:\n\n{fiche}")
    else:
        await update.message.reply_text(f"Aucune fiche pour {num}")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc: return
    log(f"Document reçu : {doc.file_name}")
    await update.message.reply_text("Traitement du fichier en cours…")
    
    file = await doc.get_file()
    data = await file.download_as_bytearray()
    text = data.decode("utf-8", errors="ignore")
    
    added, updated = import_text_into_db(text)
    await update.message.reply_text(
        f"✅ Import terminé !\n"
        f"Ajoutées : {added}\n"
        f"Mises à jour : {updated}\n"
        f"Total : {len(db)} fiches"
    )
    log(f"Import → +{added} / ~{updated} → total {len(db)}")

async def handle_plain_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Silence total sur les messages normaux → comme tu voulais
    return

# === Démarrage ===
if __name__ == "__main__":
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise SystemExit("⚠️ Variable BOT_TOKEN manquante !")

    # Chargement unique au démarrage
    global db
    db = load_db_once()

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("ping", cmd_ping))
    app.add_handler(CommandHandler("stat", cmd_stat))
    app.add_handler(CommandHandler("export", cmd_export))

    app.add_handler(MessageHandler(filters.Regex(r"^/num", re.IGNORECASE), handle_num))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_plain_text))

    print("🚀 leZbot démarré → /num ultra-rapide !")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
