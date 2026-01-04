#!/usr/bin/env python3
"""
leZbot — Telegram bot: ajoute des fiches depuis des .txt et renvoie la fiche avec /num0612345678
- Envoie un .txt (ou colle du texte) pour indexer
- /num0612345678 (ou /num 0612345678) → renvoie la fiche
- /stat → nombre de numéros
- /export → exporte toutes les fiches
Extras (debug): /ping, /debug et logs en console

NOUVELLE VERSION : Le bot NE RÉPOND PLUS quand tu lui parles normalement (ex: "jdis", "ok", "merci").
Il reste silencieux sauf pour les commandes et les fichiers.
"""

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# ✅ Fix Windows / asyncio
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

DB_PATH = Path("db.json")
MAX_REPLY = 3900
PHONE_RE = re.compile(r"(?:\+?33|0)?\s*[1-9](?:[ .-]?\d){8}")

def log(*args):
    print("[leZbot]", *args, flush=True)

def load_db() -> Dict[str, str]:
    if DB_PATH.exists():
        try:
            return json.loads(DB_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            log("DB load error:", e)
            return {}
    return {}

def save_db(db: Dict[str, str]) -> None:
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
    parts = re.split(r"\n\s*\n", text.strip())
    return [p.strip() for p in parts if p.strip()]

def index_fiche_block(block: str) -> List[Tuple[str, str]]:
    found = []
    for m in PHONE_RE.finditer(block):
        n = normalize_fr_phone(m.group())
        if n: found.append((n, block))
    seen = set(); unique = []
    for num, b in found:
        if num not in seen:
            seen.add(num); unique.append((num, b))
    return unique

def index_fiches_file(text: str) -> List[Tuple[str, str]]:
    blocks = re.findall(r"(?ms)^Fiche\s+\d+\s*\n.*?(?=^Fiche\s+\d+\s*\n|\Z)", text)
    pairs: List[Tuple[str, str]] = []
    if not blocks: return pairs
    phone_line_re = re.compile(r"^(?:T[ée]l[ée]phone\s*mobile|Mobile|Portable)\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
    for blk in blocks:
        m = phone_line_re.search(blk)
        cand = (m.group(1).strip() if m else "")
        if not cand:
            m2 = re.search(r"\b\d{9,14}\b", blk)
            cand = m2.group(0) if m2 else ""
        if not cand: continue
        num = normalize_fr_phone(cand)
        if not num: continue
        pairs.append((num, blk.strip()))
    seen: Dict[str, str] = {}
    for num, blk in pairs:
        seen[num] = blk
    return list(seen.items())

def parse_pipe_separated(text: str) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
    lines = text.strip().splitlines()
    for line in lines:
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

def import_text_into_db(text: str, db: Dict[str, str]) -> Tuple[int, int]:
    added = updated = 0
    
    lines = text.strip().splitlines()
    pipe_lines = [line for line in lines if line.count('|') >= 9]
    if len(pipe_lines) > len(lines) * 0.8 and len(lines) > 1:
        log("Format pipe-separated détecté !")
        fiche_pairs = parse_pipe_separated(text)
    else:
        fiche_pairs = index_fiches_file(text)
        if fiche_pairs:
            log(f"Format 'Fiche X' détecté : {len(fiche_pairs)} blocs")
        else:
            for block in split_fiches(text):
                pairs = index_fiche_block(block)
                if not pairs:
                    m = re.search(r"\b\d{10}\b", block)
                    if m:
                        n = normalize_fr_phone(m.group())
                        if n: pairs = [(n, block)]
                fiche_pairs.extend(pairs)
            if not fiche_pairs:
                return 0, 0
    
    for num, fiche in fiche_pairs:
        if num in db:
            if fiche != db[num]: db[num] = fiche; updated += 1
        else:
            db[num] = fiche; added += 1
    
    return added, updated

# --- Commandes ---------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    log("/start from", update.effective_user.id)
    await update.message.reply_text(
        "✅ leZbot opérationnel.\n"
        "• Envoie un fichier .txt pour ajouter des fiches (format libre, 'Fiche X' ou pipe-separated).\n"
        "• /num0612345678 → affiche la fiche.\n"
        "• /stat → nombre de numéros • /export → tout exporter.\n"
        "• /ping → test."
    )

async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    log("/ping"); await update.message.reply_text("🏓 pong")

async def cmd_debug(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = load_db()
    info = {"cwd": str(Path.cwd()), "db_exists": DB_PATH.exists(), "db_count": len(db), "python": sys.version.split()[0]}
    log("/debug", info); await update.message.reply_text(f"🛠️ DEBUG:\n{json.dumps(info, indent=2)}")

async def cmd_stat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = load_db(); log("/stat →", len(db)); await update.message.reply_text(f"📊 {len(db)} numéros indexés.")

async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = load_db(); log("/export demandé")
    if not db: await update.message.reply_text("Rien à exporter."); return
    lines = [f"===== {num} =====\n{fiche}\n" for num, fiche in sorted(db.items())]
    path = Path("export_fiches.txt"); path.write_text("\n".join(lines), encoding="utf-8")
    await update.message.reply_document(document=InputFile(path.open("rb"), filename=path.name))
    log("/export envoyé:", path)

async def handle_num(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""; log("Message num:", text)
    m = re.search(r"/num\s*([+\d][\d .-]*)", text, re.IGNORECASE)
    if not m: await update.message.reply_text("Format: /num0612345678 ou /num 0612345678"); return
    num = normalize_fr_phone(m.group(1))
    if not num: await update.message.reply_text("Numéro invalide. Exemple: /num0612345678"); return
    db = load_db(); fiche = db.get(num)
    if fiche:
        if len(fiche) > MAX_REPLY: fiche = fiche[:MAX_REPLY-50] + "\n… (fiche coupée)"
        await update.message.reply_text(f"📇 Fiche {num}:\n\n{fiche}")
    else:
        await update.message.reply_text("Aucune fiche trouvée pour ce numéro.")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    doc = update.message.document
    if not doc: return
    log(f"📂 Document reçu: {doc.file_name} ({doc.file_size} bytes)")
    await update.message.reply_text("📂 Fichier reçu, traitement en cours…")
    file = await doc.get_file(); data = await file.download_as_bytearray()
    text = data.decode("utf-8", errors="ignore")
    db = load_db(); added, updated = import_text_into_db(text, db); save_db(db)
    await update.message.reply_text(f"✅ Import terminé. Ajoutés: {added} • Mis à jour: {updated} • Total: {len(db)}")
    log(f"Import terminé → added={added}, updated={updated}, total={len(db)}")

async def handle_plain_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
    log("Texte reçu (ignoré car pas un fichier ni commande traitée ici):", text[:80])
    
    # SILENCE TOTAL : le bot ne répond RIEN quand tu lui parles normalement
    # Il ne traite plus le texte collé comme des fiches → plus de message d'erreur
    return

# --- Lancement ---------------------------------------------------------

if __name__ == "__main__":
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise SystemExit("⚠️ Défini la variable d'environnement BOT_TOKEN avec ton token BotFather.")
    
    app = Application.builder().token(token).build()
    
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("ping", cmd_ping))
    app.add_handler(CommandHandler("debug", cmd_debug))
    app.add_handler(CommandHandler("stat", cmd_stat))
    app.add_handler(CommandHandler("export", cmd_export))
    
    # /num géré séparément pour plus de flexibilité (insensible à la casse)
    app.add_handler(MessageHandler(filters.Regex(r"^/num", re.IGNORECASE), handle_num))
    
    # Fichiers .txt ou autres documents
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    # Tout texte normal → ignoré silencieusement
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_plain_text))
    
    print("✅ leZbot lancé et prêt ! (silencieux sur les messages normaux)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
