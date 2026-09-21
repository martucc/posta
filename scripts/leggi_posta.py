"""Scarica da Gmail cio' che serve al riepilogo e lo scrive in lavoro/mail.json.

Due gruppi:
  - ultime_24h: i thread con posta in inbox nelle ultime 24 ore
  - pacchi:     i thread di ordini e spedizioni degli ultimi 21 giorni

Di ogni messaggio conserviamo internalDate, il timestamp vero dell'API: e'
l'unico modo onesto di sapere quando e' arrivato. Le date scritte nel corpo
di una mail non contano, e un thread riaperto oggi puo' contenere messaggi
di tre settimane fa: quelli sono marcati recente=false e nessuno li tocchera'.
"""

import base64
import html
import json
import os
import re
import sys
from datetime import datetime, timedelta
from email.utils import parseaddr
from zoneinfo import ZoneInfo

from gmail import FUSO, RUMORE, mappa_etichette, riprova, service

Q_24H = "newer_than:2d -in:sent -in:draft -in:chats"
Q_PACCHI = ("newer_than:21d -in:sent -in:draft "
            "subject:(ordine OR spedizione OR spedito OR consegna OR consegnato OR pacco "
            "OR tracking OR shipped OR delivered OR order OR reso OR rimborso OR refund "
            "OR ritiro OR locker)")

MAX_CORPO = 2500
MAX_DIMENSIONE = 500_000
FINESTRA_ORE = 24

GIORNI = ["LUN", "MAR", "MER", "GIO", "VEN", "SAB", "DOM"]
MESI = ["GEN", "FEB", "MAR", "APR", "MAG", "GIU", "LUG", "AGO", "SET", "OTT", "NOV", "DIC"]


def id_thread(svc, q):
    ids, token = [], None
    while True:
        r = riprova(svc.users().threads().list(userId="me", q=q, maxResults=100,
                                               pageToken=token), "elenco thread")
        ids += [t["id"] for t in r.get("threads", [])]
        token = r.get("nextPageToken")
        if not token:
            return ids


def testo_di(payload):
    """Primo text/plain, altrimenti l'HTML ripulito. I link lunghissimi, che
    sono quasi sempre tracker o token, diventano [link]."""
    piano, ricco = [], []

    def scorri(p):
        dati = p.get("body", {}).get("data")
        mime = p.get("mimeType", "")
        if dati and mime == "text/plain":
            piano.append(base64.urlsafe_b64decode(dati).decode("utf-8", "replace"))
        elif dati and mime == "text/html":
            ricco.append(base64.urlsafe_b64decode(dati).decode("utf-8", "replace"))
        for parte in p.get("parts", []):
            scorri(parte)

    scorri(payload)
    if piano:
        testo = piano[0]
    elif ricco:
        testo = re.sub(r"(?is)<(style|script)[^>]*>.*?</\1>", " ", ricco[0])
        testo = html.unescape(re.sub(r"<[^>]+>", " ", testo))
    else:
        return ""
    testo = re.sub(r"https?://\S{60,}", "[link]", testo)
    return re.sub(r"\s+", " ", testo).strip()[:MAX_CORPO]


def messaggio(m, nomi, taglio_ms):
    intestazioni = {h["name"].lower(): h["value"] for h in m["payload"].get("headers", [])}
    ids = m.get("labelIds", [])
    etichette = sorted({nomi[i] for i in ids if i in nomi})
    interna = int(m.get("internalDate", 0))
    fuori = {"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "SPAM", "TRASH"}
    out = {
        "messageId": m["id"],
        "threadId": m["threadId"],
        "labelIds": ids,
        "etichette": etichette,
        "recente": interna >= taglio_ms,
        "in_inbox": "INBOX" in ids,
        "arrivata": datetime.fromtimestamp(interna / 1000, ZoneInfo(FUSO)).isoformat(timespec="minutes"),
        "from": intestazioni.get("from", ""),
        "fromAddress": parseaddr(intestazioni.get("from", ""))[1].lower(),
        "subject": intestazioni.get("subject", ""),
        "snippet": html.unescape(m.get("snippet", "")),
    }
    # Di promo e social passa solo lo snippet: meno superficie per un'iniezione
    # e meno rumore da leggere.
    rumorosa = set(etichette) & RUMORE or set(ids) & fuori
    if not rumorosa and m.get("sizeEstimate", 0) <= MAX_DIMENSIONE:
        out["corpo"] = testo_di(m["payload"])
    return out


def main(destinazione):
    svc = service()
    nomi = {i: n for n, i in mappa_etichette(svc).items()}
    adesso = datetime.now(ZoneInfo(FUSO))
    taglio = adesso - timedelta(hours=FINESTRA_ORE)
    taglio_ms = int(taglio.timestamp() * 1000)

    dati = {
        "oggi": f"{GIORNI[adesso.weekday()]} {adesso.day:02d} {MESI[adesso.month - 1]} {adesso.year}",
        "oggi_iso": adesso.date().isoformat(),
        "stamp": adesso.strftime("%d.%m"),
        "adesso": adesso.isoformat(timespec="minutes"),
        "finestra_da": taglio.isoformat(timespec="minutes"),
        "etichette_disponibili": sorted(nomi.values()),
    }
    for gruppo, q in (("ultime_24h", Q_24H), ("pacchi", Q_PACCHI)):
        thread = []
        for tid in id_thread(svc, q):
            t = riprova(svc.users().threads().get(userId="me", id=tid, format="full"),
                        f"thread {tid}")
            messaggi = [messaggio(m, nomi, taglio_ms) for m in t["messages"]]
            if gruppo == "ultime_24h" and not any(m["recente"] for m in messaggi):
                continue  # newer_than:2d e' largo apposta, qui stringiamo a 24h vere
            thread.append({"threadId": tid, "messages": messaggi})
        dati[gruppo] = thread

    cartella = os.path.dirname(destinazione)
    if cartella:
        os.makedirs(cartella, exist_ok=True)
    with open(destinazione, "w", encoding="utf-8") as f:
        json.dump(dati, f, ensure_ascii=False, indent=1)
    recenti = sum(1 for t in dati["ultime_24h"] for m in t["messages"] if m["recente"])
    print(f"{len(dati['ultime_24h'])} thread nelle ultime 24 ore ({recenti} messaggi), "
          f"{len(dati['pacchi'])} thread di pacchi")


if __name__ == "__main__":
    main(sys.argv[1])
