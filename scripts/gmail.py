"""Connessione a Gmail condivisa dagli script della Posta della sera.

Il token arriva dal secret GMAIL_TOKEN_JSON: e lo stesso contenuto di
token.json di gmail-summarizer (client_id, client_secret, refresh_token).
"""

import json
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

ME = "2005niky@gmail.com"
TLDR = "dan@tldrnewsletter.com"

# Le uniche etichette che Claude puo proporre.
LABELS = {
    "Label_69": "Ordini/Confermati", "Label_58": "Ordini/In consegna",
    "Label_70": "Ordini/Resi e rimborsi", "Label_65": "Soldi/Banca",
    "Label_68": "Soldi/Investimenti", "Label_56": "Sicurezza", "Label_50": "Viaggi",
    "Label_62": "Eventi", "Label_55": "Progetti", "Label_76": "Lavoro/Offerte",
    "Label_77": "Lavoro/Clienti", "Label_71": "Newsletter/Tech", "Label_52": "Promo",
    "Label_72": "Promo/Moda", "Label_73": "Promo/Beauty", "Label_74": "Promo/Sport",
    "Label_75": "Promo/Tech", "Label_51": "Social", "Label_78": "Scommesse",
    "Label_60": "Personale", "Label_66": "Studio", "Label_64": "Salute",
}

# Promo, Promo/*, Social, Scommesse: vanno archiviate.
RUMORE = {"Label_52", "Label_72", "Label_73", "Label_74", "Label_75", "Label_51", "Label_78"}


def service():
    info = json.loads(os.environ["GMAIL_TOKEN_JSON"])
    creds = Credentials.from_authorized_user_info(info, SCOPES)
    if not creds.valid:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)
