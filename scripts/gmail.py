"""Connessione a Gmail e regole che valgono per tutti gli script della Posta.

Tre principi, e sono qui e non nel prompt cosi' nessuna mail puo' cambiarli:
  - le etichette si risolvono per NOME contro l'account, mai per ID cablato
  - le operazioni distruttive hanno una lista chiusa scritta in questo file
  - DRY_RUN=1 spegne ogni scrittura, senza toccare il resto del codice
"""

import json
import os
import random
import re
import time

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# gmail.modify copre etichette, archivio, cestino e invio. Basta questo:
# mail.google.com darebbe anche la cancellazione definitiva, che non ci serve.
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

DRY_RUN = os.environ.get("DRY_RUN", "").strip().lower() in {"1", "true", "si", "yes"}
ME = os.environ.get("OWNER_EMAIL", "").strip().lower()
PAGINA = os.environ.get("PAGE_URL", "").strip()
FUSO = os.environ.get("TIMEZONE", "Europe/Rome")

# Mittenti le cui mail possono finire nel cestino. Lista chiusa, confrontata
# sull'indirizzo esatto del mittente: la parola "TLDR" nel corpo non conta.
CESTINO = {m.strip().lower() for m in
           os.environ.get("TRASH_SENDERS", "dan@tldrnewsletter.com").split(",") if m.strip()}

# Le uniche etichette che l'automazione puo' applicare, per nome.
ETICHETTE = [
    "Ordini/Confermati", "Ordini/In consegna", "Ordini/Resi e rimborsi",
    "Soldi/Banca", "Soldi/Investimenti", "Sicurezza", "Viaggi", "Eventi", "Progetti",
    "Lavoro/Offerte", "Lavoro/Clienti", "Newsletter/Tech",
    "Promo", "Promo/Moda", "Promo/Beauty", "Promo/Sport", "Promo/Tech",
    "Social", "Scommesse", "Personale", "Studio", "Salute",
]

# Quelle che, da sole, fanno di una mail del rumore da archiviare.
RUMORE = {"Promo", "Promo/Moda", "Promo/Beauty", "Promo/Sport", "Promo/Tech",
          "Social", "Scommesse"}

# Se una mail ha anche una di queste, resta in inbox anche se e' promozionale:
# una conferma d'ordine dentro una newsletter di negozio vale piu' della promo.
SALVAGENTE = {"Ordini/Confermati", "Ordini/In consegna", "Ordini/Resi e rimborsi",
              "Sicurezza", "Soldi/Banca", "Soldi/Investimenti", "Viaggi",
              "Lavoro/Offerte", "Lavoro/Clienti"}

RIPROVABILI = {403, 429, 500, 502, 503, 504}
TENTATIVI = 5


class Configurazione(RuntimeError):
    """Manca qualcosa nell'ambiente: meglio fermarsi subito che a meta' serata."""


def controlla_ambiente(serve_pagina=False):
    mancanti = []
    if not ME or "@" not in ME:
        mancanti.append("OWNER_EMAIL")
    if not os.environ.get("GMAIL_TOKEN_JSON"):
        mancanti.append("GMAIL_TOKEN_JSON")
    if serve_pagina and not PAGINA.startswith("https://"):
        mancanti.append("PAGE_URL")
    if mancanti:
        raise Configurazione("variabili d'ambiente mancanti: " + ", ".join(mancanti))


def riprova(chiamata, cosa="chiamata Gmail"):
    """Backoff esponenziale con jitter: i 429 e i 5xx di Google passano da soli,
    gli altri errori no e non ha senso insistere."""
    for tentativo in range(TENTATIVI):
        try:
            return chiamata.execute()
        except HttpError as errore:
            codice = getattr(errore.resp, "status", None)
            if codice not in RIPROVABILI or tentativo == TENTATIVI - 1:
                raise
            attesa = min(2 ** tentativo, 16) + random.random()
            print(f"{cosa}: errore {codice}, riprovo fra {attesa:.1f}s")
            time.sleep(attesa)
    raise RuntimeError("irraggiungibile")


def service():
    controlla_ambiente()
    try:
        info = json.loads(os.environ["GMAIL_TOKEN_JSON"])
    except ValueError as errore:
        raise Configurazione(f"GMAIL_TOKEN_JSON non e' JSON valido: {errore}") from None
    creds = Credentials.from_authorized_user_info(info, SCOPES)
    if not creds.valid:
        if not creds.refresh_token:
            raise Configurazione(
                "il token non ha refresh_token: rigenera token.json con autorizza.py")
        try:
            creds.refresh(Request())
        except Exception as errore:  # token revocato, client cambiato, rete
            raise Configurazione(
                f"rinnovo del token fallito ({errore}): probabilmente hai revocato "
                "l'accesso, rigenera token.json con autorizza.py") from None
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def mappa_etichette(svc):
    """Nome -> ID, letto dall'account. Se una manca lo dice e va avanti senza:
    meglio una mail senza etichetta che una mail nell'etichetta sbagliata."""
    risposta = riprova(svc.users().labels().list(userId="me"), "elenco etichette")
    presenti = {l["name"]: l["id"] for l in risposta.get("labels", [])}
    mappa = {nome: presenti[nome] for nome in ETICHETTE if nome in presenti}
    mancanti = [nome for nome in ETICHETTE if nome not in presenti]
    if mancanti:
        print(f"ATTENZIONE: etichette non trovate in Gmail, non verranno usate: {', '.join(mancanti)}")
    return mappa


def pulisci_oggetto(testo, ripiego="Posta della sera"):
    """Un oggetto con un a capo dentro diventa un'iniezione di header SMTP."""
    pulito = re.sub(r"[\r\n\t]+", " ", str(testo or "")).strip()
    return pulito[:180] or ripiego
