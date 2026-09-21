"""Applica a Gmail le decisioni di Claude, con i limiti scritti qui e non nel prompt.

- etichette: solo le ID di LABELS, solo su messaggi scaricati da leggi_posta.py
- archivio: solo il rumore (RUMORE) arrivato nelle ultime 24 ore
- cestino: solo i messaggi il cui mittente e TLDR, verificato qui
- email: una sola, sempre e solo a ME
"""

import base64
import json
import os
import sys
from email.mime.text import MIMEText

from gmail import LABELS, ME, RUMORE, TLDR, service

LINK = "https://martucc.github.io/posta/"


def load(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def read_text(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def main(workdir):
    mail = load(os.path.join(workdir, "mail.json"))
    azioni = load(os.path.join(workdir, "azioni.json"), {})
    push = read_text(os.path.join(workdir, "esito_push.txt"))
    svc = service()

    messages = {}
    for group in ("ultime_24h", "pacchi"):
        for t in (mail or {}).get(group, []):
            for m in t["messages"]:
                messages[m["messageId"]] = m
    recent = {m["messageId"] for t in (mail or {}).get("ultime_24h", []) for m in t["messages"]}

    # Etichette
    added = {}
    for e in azioni.get("etichette", []):
        mid, lid = e.get("messageId"), e.get("labelId")
        if mid in messages and lid in LABELS and lid not in messages[mid]["labelIds"]:
            added.setdefault(mid, set()).add(lid)
        else:
            print(f"etichetta ignorata: {e}")
    for mid, lids in added.items():
        svc.users().messages().modify(userId="me", id=mid, body={"addLabelIds": sorted(lids)}).execute()

    # Cestino TLDR e archivio del rumore
    trashed = archived = 0
    for mid in recent:
        m = messages[mid]
        if m["fromAddress"] == TLDR:
            svc.users().messages().trash(userId="me", id=mid).execute()
            trashed += 1
        elif "INBOX" in m["labelIds"] and (set(m["labelIds"]) | added.get(mid, set())) & RUMORE:
            svc.users().messages().modify(userId="me", id=mid, body={"removeLabelIds": ["INBOX"]}).execute()
            archived += 1
    print(f"{sum(map(len, added.values()))} etichette, {archived} archiviate, {trashed} TLDR nel cestino")

    # Email di avviso
    email = azioni.get("email") or {}
    subject = str(email.get("oggetto") or "Posta della sera: riepilogo non generato").strip()[:200]
    lines = [str(r).strip() for r in email.get("righe", []) if str(r).strip()][:5]
    if mail is None:
        lines = ["Non sono riuscito a leggere Gmail: guarda il log del workflow."]
    elif not azioni:
        lines = ["Claude non ha prodotto il riepilogo: guarda il log del workflow."]
    if push:
        lines.insert(0, push)
    body = "\n".join(lines + ["", LINK])
    msg = MIMEText(body, "plain", "utf-8")
    msg["To"] = ME
    msg["From"] = ME
    msg["Subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    svc.users().messages().send(userId="me", body={"raw": raw}).execute()
    print(f"avviso inviato: {subject}")


if __name__ == "__main__":
    main(sys.argv[1])
