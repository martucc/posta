"""Applica a Gmail le decisioni della serata, con i limiti scritti qui.

Il modello e' quello: chi decide non ha i permessi, chi ha i permessi non
legge le mail. Questo script non si fida di niente di quello che arriva in
azioni.json — controlla ogni messageId, ogni etichetta, ogni destinatario
contro dati che ha raccolto lui.

Con DRY_RUN=1 non scrive niente: stampa cosa avrebbe fatto ed esce.
"""

import base64
import json
import os
import sys
from email.mime.text import MIMEText

from gmail import (CESTINO, DRY_RUN, ME, PAGINA, RUMORE, SALVAGENTE, Configurazione,
                   mappa_etichette, pulisci_oggetto, riprova, service)

MARCATORE = "posta-della-sera"


def carica(percorso, ripiego=None):
    try:
        with open(percorso, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return ripiego


def leggi(percorso):
    try:
        with open(percorso, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def indice(mail):
    """Tutti i messaggi scaricati, e l'insieme di quelli su cui e' lecito agire:
    arrivati davvero nelle ultime 24 ore, non gia' nel cestino."""
    messaggi, agibili = {}, set()
    for gruppo in ("ultime_24h", "pacchi"):
        for t in (mail or {}).get(gruppo, []):
            for m in t["messages"]:
                messaggi[m["messageId"]] = m
    for t in (mail or {}).get("ultime_24h", []):
        for m in t["messages"]:
            if m.get("recente") and "TRASH" not in m.get("labelIds", []):
                agibili.add(m["messageId"])
    return messaggi, agibili


def etichette_da_applicare(azioni, messaggi, agibili, mappa):
    """Tiene solo le proposte che superano tutti i controlli, e dice ad alta
    voce quali scarta e perche'."""
    scelte, scartate = {}, []
    for e in azioni.get("etichette", []):
        mid = e.get("messageId")
        nome = e.get("etichetta")
        if mid not in agibili:
            scartate.append(f"{mid}: non e' fra i messaggi recenti scaricati")
        elif nome not in mappa:
            scartate.append(f"{mid}: etichetta '{nome}' non esiste o non e' consentita")
        elif nome in messaggi[mid].get("etichette", []):
            pass  # gia' etichettata: non e' un errore, e' idempotenza
        else:
            scelte.setdefault(mid, set()).add(nome)
    for riga in scartate[:10]:
        print(f"etichetta ignorata — {riga}")
    if len(scartate) > 10:
        print(f"...e altre {len(scartate) - 10} ignorate")
    return scelte


def decidi_archivio(mid, messaggi, scelte):
    """Rumore si', ma non se dentro c'e' qualcosa di operativo."""
    m = messaggi[mid]
    finali = set(m.get("etichette", [])) | scelte.get(mid, set())
    if not m.get("in_inbox"):
        return False
    if finali & SALVAGENTE:
        return False
    return bool(finali & RUMORE)


def gia_mandata(svc, oggi):
    """Se il riepilogo di oggi e' gia' partito, non ne mandiamo un secondo.
    Lo stato sta in Gmail: nessun database da tenere in vita."""
    try:
        r = riprova(svc.users().messages().list(
            userId="me", q=f'in:anywhere from:{ME} "{MARCATORE}:{oggi}"', maxResults=1),
            "controllo riepilogo gia' inviato")
        return bool(r.get("messages"))
    except Exception as errore:
        print(f"non sono riuscito a verificare se il riepilogo era gia' partito: {errore}")
        return False


def manda(svc, oggetto, righe, oggi):
    corpo = "\n".join(righe + ["", PAGINA, "", f"{MARCATORE}:{oggi}"])
    msg = MIMEText(corpo, "plain", "utf-8")
    msg["To"] = ME
    msg["From"] = ME
    msg["Subject"] = pulisci_oggetto(oggetto)
    grezzo = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    riprova(svc.users().messages().send(userId="me", body={"raw": grezzo}), "invio riepilogo")


def main(cartella):
    mail = carica(os.path.join(cartella, "mail.json"))
    azioni = carica(os.path.join(cartella, "azioni.json"), {}) or {}
    esito_pagina = leggi(os.path.join(cartella, "esito_pagina.txt"))
    oggi = (mail or {}).get("oggi_iso", "")

    svc = service()
    mappa = mappa_etichette(svc)
    messaggi, agibili = indice(mail)
    scelte = etichette_da_applicare(azioni, messaggi, agibili, mappa)

    da_archiviare = [mid for mid in agibili if decidi_archivio(mid, messaggi, scelte)]
    da_cestinare = [mid for mid in agibili
                    if messaggi[mid].get("fromAddress") in CESTINO]
    da_archiviare = [mid for mid in da_archiviare if mid not in da_cestinare]

    quante = sum(len(v) for v in scelte.values())
    print(f"{quante} etichette su {len(scelte)} messaggi, "
          f"{len(da_archiviare)} da archiviare, {len(da_cestinare)} nel cestino")

    if DRY_RUN:
        for mid, nomi in sorted(scelte.items()):
            print(f"  [dry-run] etichetta {mid}: {', '.join(sorted(nomi))}")
        for mid in da_archiviare:
            print(f"  [dry-run] archivia {mid}: {messaggi[mid]['subject'][:60]}")
        for mid in da_cestinare:
            print(f"  [dry-run] cestino {mid}: da {messaggi[mid]['fromAddress']}")
        oggetto = pulisci_oggetto((azioni.get("email") or {}).get("oggetto"))
        print(f"  [dry-run] email a {ME}: {oggetto}")
        for riga in (azioni.get("email") or {}).get("righe", [])[:5]:
            print(f"  [dry-run]   {riga}")
        print("DRY_RUN: nessuna modifica eseguita")
        return

    for mid, nomi in scelte.items():
        ids = sorted(mappa[n] for n in nomi)
        riprova(svc.users().messages().modify(userId="me", id=mid,
                                              body={"addLabelIds": ids}), "etichetta")
    for mid in da_archiviare:
        riprova(svc.users().messages().modify(userId="me", id=mid,
                                              body={"removeLabelIds": ["INBOX"]}), "archivio")
    for mid in da_cestinare:
        riprova(svc.users().messages().trash(userId="me", id=mid), "cestino")

    email = azioni.get("email") or {}
    righe = [str(r).strip() for r in email.get("righe", []) if str(r).strip()][:5]
    if mail is None:
        righe = ["Non sono riuscito a leggere Gmail: guarda il log del workflow."]
    elif not azioni:
        righe = ["Il riepilogo non e' stato generato: guarda il log del workflow."]
    elif not righe:
        righe = [f"Serata tranquilla. {len(da_archiviare)} mail di rumore archiviate."]
    if esito_pagina:
        righe.insert(0, esito_pagina)  # il fallimento e' sempre la prima riga

    if oggi and gia_mandata(svc, oggi):
        print("riepilogo di oggi gia' inviato, non ne mando un altro")
        return
    manda(svc, email.get("oggetto") or "Posta della sera", righe, oggi)
    print(f"riepilogo inviato: {pulisci_oggetto(email.get('oggetto'))}")


if __name__ == "__main__":
    try:
        main(sys.argv[1])
    except Configurazione as errore:
        print(f"configurazione incompleta: {errore}")
        sys.exit(2)
