"""Ultima difesa prima della pubblicazione: la pagina e' pubblica per sempre.

Controlla tre cose diverse, in quest'ordine:
  1. che il design sia intatto  — testa e coda identiche alla versione precedente
  2. che l'HTML regga           — tag bilanciati, solo classi che il CSS conosce
  3. che non ci siano segreti   — IBAN, carte, OTP, token, password

Esce 1 e stampa cosa non va. Chi lo chiama non deve pubblicare.
"""

import re
import sys
from html.parser import HTMLParser

CLASSI_NOTE = {
    "page", "head", "brandline", "mark", "brand", "install", "stamp", "hl", "dateline",
    "board", "urg", "perf", "stack", "sec-head", "n", "rule", "note", "rows",
    "card", "urgent", "row", "row-top", "who", "arrow", "tag", "ok", "go", "warn", "crit",
    "meta", "route", "done", "now", "foot", "btn", "hint",
    "cash", "amt", "in", "out", "zero", "cash-txt", "quiet", "split",
}
SEZIONI_ATTESE = ["Pacchi", "Da fare", "Soldi", "Viaggi", "Progetti", "Lavoro", "Rumore"]
VUOTI = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
         "meta", "param", "source", "track", "wbr", "path", "circle", "rect", "polygon", "line"}

SEGRETI = [
    (re.compile(r"\b(?:password|passwd|pwd)\b\s*[:=]", re.I), "una password"),
    (re.compile(r"\b(?:otp|codice di verifica|verification code|one[- ]time code)\b", re.I), "un codice OTP"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._-]{12,}", re.I), "un token Bearer"),
    (re.compile(r"\b(?:gh[pousr]|github_pat)_[A-Za-z0-9_]{20,}"), "un token GitHub"),
    (re.compile(r"\bya29\.[A-Za-z0-9._-]{20,}"), "un access token Google"),
    (re.compile(r"\bAIza[A-Za-z0-9_-]{30,}"), "una API key Google"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "una chiave privata"),
    (re.compile(r"\bpin\b\s*[:=]?\s*\d{4,8}\b", re.I), "un PIN"),
]


class Bilancio(HTMLParser):
    """Tag aperti e chiusi devono tornare. Non e' un validatore W3C: serve a
    non pubblicare una pagina spezzata a meta'."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pila, self.errori, self.classi = [], [], set()

    def handle_starttag(self, tag, attrs):
        for nome, valore in attrs:
            if nome == "class" and valore:
                self.classi.update(valore.split())
        if tag not in VUOTI:
            self.pila.append((tag, self.getpos()[0]))

    def handle_startendtag(self, tag, attrs):
        for nome, valore in attrs:
            if nome == "class" and valore:
                self.classi.update(valore.split())

    def handle_endtag(self, tag):
        if tag in VUOTI:
            return
        if not self.pila:
            self.errori.append(f"</{tag}> chiude un tag mai aperto")
        elif self.pila[-1][0] != tag:
            aperto, riga = self.pila[-1]
            self.errori.append(f"</{tag}> chiude <{aperto}> aperto alla riga {riga}")
            self.pila.pop()
        else:
            self.pila.pop()


def luhn(cifre):
    totale = 0
    for i, d in enumerate(reversed(cifre)):
        n = int(d)
        if i % 2:
            n = n * 2 - 9 if n > 4 else n * 2
        totale += n
    return totale % 10 == 0


def iban_valido(iban):
    """Checksum mod-97: esclude i tracking che per caso hanno la forma di un IBAN."""
    spostato = iban[4:] + iban[:4]
    try:
        return int("".join(str(int(c, 36)) for c in spostato)) % 97 == 1
    except ValueError:
        return False


def taglia(pagina):
    fine_head = pagina.find("</head>")
    apre_body = pagina.find("<body>", fine_head)
    ultimo_script = pagina.rfind("<script>")
    if fine_head < 0 or apre_body < 0 or ultimo_script < apre_body:
        return None
    fine = apre_body + len("<body>")
    return pagina[:fine], pagina[fine:ultimo_script], pagina[ultimo_script:]


def controlla_struttura(nuova, precedente, problemi):
    pezzi = taglia(nuova)
    if not pezzi:
        problemi.append("la pagina non ha piu' la struttura </head> / <body> / <script>")
        return None
    testa, corpo, coda = pezzi
    if precedente is not None:
        prima = taglia(precedente)
        if prima:
            if testa != prima[0]:
                problemi.append("la testa della pagina (head, font, CSS) e' cambiata")
            if coda != prima[2]:
                problemi.append("lo script finale (service worker, bottone Installa) e' cambiato")
    for pezzo, cosa in (('rel="manifest"', "il link al manifest"),
                        ("serviceWorker.register", "la registrazione del service worker"),
                        ('id="install"', "il bottone Installa")):
        if pezzo not in nuova:
            problemi.append(f"manca {cosa}")
    return corpo


def controlla_html(corpo, problemi):
    b = Bilancio()
    b.feed(corpo)
    problemi.extend(b.errori[:5])
    if b.pila:
        aperti = ", ".join(f"<{t}> riga {r}" for t, r in b.pila[:5])
        problemi.append(f"tag rimasti aperti: {aperti}")
    sconosciute = sorted(b.classi - CLASSI_NOTE)
    if sconosciute:
        problemi.append(f"classi CSS che non esistono nel foglio di stile: {', '.join(sconosciute[:5])}")


def controlla_sezioni(corpo, problemi):
    titoli = re.findall(r"<h2>([^<]+)</h2>", corpo)
    fuori = [t for t in titoli if t not in SEZIONI_ATTESE and t != "Serata tranquilla"]
    if fuori:
        problemi.append(f"sezioni non previste: {', '.join(fuori)}")
    conosciuti = [t for t in titoli if t in SEZIONI_ATTESE]
    if conosciuti != sorted(conosciuti, key=SEZIONI_ATTESE.index):
        problemi.append(f"le sezioni sono fuori ordine: {' · '.join(conosciuti)}")
    # Il contatore di ogni sezione deve dire quante schede ci sono davvero.
    for blocco in re.findall(r"<h2>([^<]+)</h2><span class=\"n\">(\d+)</span>(.*?)</section>",
                             corpo, re.S):
        titolo, dichiarato, resto = blocco
        if titolo == "Rumore":
            continue
        vere = len(re.findall(r'<div class="card', resto))
        if int(dichiarato) != vere:
            problemi.append(f"sezione {titolo}: il contatore dice {int(dichiarato)}, le schede sono {vere}")


def controlla_segreti(corpo, problemi):
    testo = re.sub(r"<[^>]+>", " ", corpo)
    for iban in re.findall(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]){11,30}\b", testo):
        compatto = iban.replace(" ", "")
        if iban_valido(compatto):
            problemi.append(f"IBAN che finisce con {compatto[-4:]}")
    carte = re.findall(r"\b\d{4}[ -]\d{4}[ -]\d{4}[ -]\d{2,4}\b", testo)
    carte += re.findall(r"\b[345]\d{14,15}\b", testo)
    for carta in carte:
        cifre = re.sub(r"\D", "", carta)
        if luhn(cifre):
            problemi.append(f"possibile numero di carta che finisce con {cifre[-4:]}")
    for schema, cosa in SEGRETI:
        if schema.search(testo) or schema.search(corpo):
            problemi.append(f"la pagina sembra contenere {cosa}")


def controlla(nuova, precedente=None):
    problemi = []
    corpo = controlla_struttura(nuova, precedente, problemi)
    if corpo is not None:
        controlla_html(corpo, problemi)
        controlla_sezioni(corpo, problemi)
        controlla_segreti(corpo, problemi)
    return problemi


def main(percorso, percorso_precedente=None):
    with open(percorso, encoding="utf-8") as f:
        nuova = f.read()
    precedente = None
    if percorso_precedente:
        try:
            with open(percorso_precedente, encoding="utf-8") as f:
                precedente = f.read()
        except OSError:
            pass
    problemi = controlla(nuova, precedente)
    if problemi:
        print("; ".join(problemi))
        sys.exit(1)
    print("pagina valida")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
