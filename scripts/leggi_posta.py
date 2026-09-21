"""Scarica da Gmail le mail che servono al riepilogo e le scrive in lavoro/mail.json.

Due gruppi:
- ultime_24h: inbox delle ultime 24 ore (niente inviate, niente bozze)
- pacchi: thread di ordini e spedizioni degli ultimi 21 giorni
Delle promo e dei social passa solo lo snippet, non il corpo.
"""

import base64
import html
import json
import os
import re
import sys
from datetime import datetime
from email.utils import parseaddr
from zoneinfo import ZoneInfo

from gmail import RUMORE, service

Q_24H = "newer_than:1d -in:sent -in:draft"
Q_PACCHI = ("newer_than:21d subject:(ordine OR spedizione OR spedito OR consegna OR consegnato "
            "OR pacco OR tracking OR shipped OR delivered OR order OR reso OR rimborso)")

MAX_BODY = 2500
MAX_SIZE = 500_000
SOLO_SNIPPET = RUMORE | {"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL"}

GIORNI = ["LUN", "MAR", "MER", "GIO", "VEN", "SAB", "DOM"]
MESI = ["GEN", "FEB", "MAR", "APR", "MAG", "GIU", "LUG", "AGO", "SET", "OTT", "NOV", "DIC"]


def thread_ids(svc, q):
    ids, token = [], None
    while True:
        r = svc.users().threads().list(userId="me", q=q, maxResults=100, pageToken=token).execute()
        ids += [t["id"] for t in r.get("threads", [])]
        token = r.get("nextPageToken")
        if not token:
            return ids


def text_of(payload):
    """Primo text/plain, altrimenti text/html ripulito."""
    plain, rich = [], []

    def walk(p):
        data = p.get("body", {}).get("data")
        mime = p.get("mimeType", "")
        if data and mime == "text/plain":
            plain.append(base64.urlsafe_b64decode(data).decode("utf-8", "replace"))
        elif data and mime == "text/html":
            rich.append(base64.urlsafe_b64decode(data).decode("utf-8", "replace"))
        for part in p.get("parts", []):
            walk(part)

    walk(payload)
    if plain:
        text = plain[0]
    elif rich:
        text = re.sub(r"(?is)<(style|script)[^>]*>.*?</\1>", " ", rich[0])
        text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    else:
        return ""
    text = re.sub(r"https?://\S{60,}", "[link]", text)
    return re.sub(r"\s+", " ", text).strip()[:MAX_BODY]


def message(m):
    headers = {h["name"].lower(): h["value"] for h in m["payload"].get("headers", [])}
    labels = m.get("labelIds", [])
    out = {
        "messageId": m["id"],
        "threadId": m["threadId"],
        "labelIds": labels,
        "from": headers.get("from", ""),
        "fromAddress": parseaddr(headers.get("from", ""))[1].lower(),
        "subject": headers.get("subject", ""),
        "date": headers.get("date", ""),
        "snippet": html.unescape(m.get("snippet", "")),
    }
    if not (set(labels) & SOLO_SNIPPET) and m.get("sizeEstimate", 0) <= MAX_SIZE:
        out["body"] = text_of(m["payload"])
    return out


def main(dest):
    svc = service()
    now = datetime.now(ZoneInfo("Europe/Rome"))
    data = {
        "oggi": f"{GIORNI[now.weekday()]} {now.day:02d} {MESI[now.month - 1]} {now.year}",
        "oggi_iso": now.date().isoformat(),
        "stamp": now.strftime("%d.%m"),
    }
    for group, q in (("ultime_24h", Q_24H), ("pacchi", Q_PACCHI)):
        threads = []
        for tid in thread_ids(svc, q):
            t = svc.users().threads().get(userId="me", id=tid, format="full").execute()
            threads.append({"threadId": tid, "messages": [message(m) for m in t["messages"]]})
        data[group] = threads
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"{len(data['ultime_24h'])} thread nelle ultime 24 ore, {len(data['pacchi'])} thread di pacchi")


if __name__ == "__main__":
    main(sys.argv[1])
