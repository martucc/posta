"""Schema e validazione di lavoro/giornata.json, il modello dati della serata.

Claude produce questo file e nient'altro che riguardi la pagina: l'HTML lo
costruisce rendi.py. Qui dentro c'e' l'unica definizione di cosa e' lecito,
e ogni errore e' un messaggio in italiano che dice dove guardare.
"""

import re

TAPPE = 4
STILI_TAG = {"ok", "go", "warn", "crit"}
STILI_IMPORTO = {"in", "out", "zero"}
STATI_TAPPA = {"done", "now", "futuro"}

# Ordine delle sezioni in pagina: non e' negoziabile, il renderer lo impone.
SEZIONI = [
    ("pacchi", "Pacchi"),
    ("da_fare", "Da fare"),
    ("soldi", "Soldi"),
    ("viaggi", "Viaggi"),
    ("progetti", "Progetti"),
    ("lavoro", "Lavoro"),
]
NOMI_SEZIONI = [k for k, _ in SEZIONI]

THREAD_ID = re.compile(r"^[0-9a-f]{8,24}$")
URL_OK = re.compile(r"^https://[^\s\"'<>]+$")
STAMP = re.compile(r"^\d{2}\.\d{2}$")
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Quello che non deve mai finire in una pagina pubblica, per quanto Claude
# sia convinto che serva. controlla_pagina.py ricontrolla sull'HTML finito.
VIETATO = re.compile(
    r"\b(password|passwd|otp|one[- ]time|codice di verifica|verification code|"
    r"pin\b|token|api[_ -]?key|secret|bearer |iban)\b", re.I)


class Errore(ValueError):
    """Dati non validi: il messaggio dice il campo e il perche'."""


def _campo(dove, chiave):
    return f"{dove}.{chiave}" if dove else chiave


def testo(valore, dove, massimo=600, obbligatorio=True):
    if valore is None and not obbligatorio:
        return None
    if not isinstance(valore, str) or not valore.strip():
        raise Errore(f"{dove}: manca il testo")
    v = valore.strip()
    if len(v) > massimo:
        raise Errore(f"{dove}: troppo lungo ({len(v)} caratteri, massimo {massimo})")
    if VIETATO.search(v):
        raise Errore(f"{dove}: contiene una parola vietata in pagina pubblica")
    return v


def intero(valore, dove, minimo=0, massimo=9999):
    if isinstance(valore, bool) or not isinstance(valore, int):
        raise Errore(f"{dove}: deve essere un numero intero")
    if not minimo <= valore <= massimo:
        raise Errore(f"{dove}: {valore} fuori dall'intervallo {minimo}-{massimo}")
    return valore


def url(valore, dove, obbligatorio=True):
    if valore is None and not obbligatorio:
        return None
    if not isinstance(valore, str) or not URL_OK.match(valore):
        raise Errore(f"{dove}: serve un URL https valido")
    if VIETATO.search(valore):
        raise Errore(f"{dove}: l'URL sembra contenere un token o una credenziale")
    return valore


def thread(valore, dove):
    if not isinstance(valore, str) or not THREAD_ID.match(valore):
        raise Errore(f"{dove}: threadId non valido ({valore!r})")
    return valore


def tag(valore, dove):
    if valore is None:
        return None
    if not isinstance(valore, dict):
        raise Errore(f"{dove}: il tag deve essere un oggetto")
    stile = valore.get("stile")
    if stile not in STILI_TAG:
        raise Errore(f"{dove}.stile: dev'essere uno fra {sorted(STILI_TAG)}")
    return {"testo": testo(valore.get("testo"), _campo(dove, "testo"), 40), "stile": stile}


def route(valore, dove):
    """La timeline del pacco: sempre quattro tappe, una sola 'now', nessuna
    tappa futura marcata come fatta."""
    if valore is None:
        return None
    if not isinstance(valore, list) or len(valore) != TAPPE:
        raise Errore(f"{dove}: la timeline deve avere esattamente {TAPPE} tappe")
    tappe, visto_now = [], False
    for i, t in enumerate(valore):
        d = _campo(dove, f"[{i}]")
        if not isinstance(t, dict):
            raise Errore(f"{d}: ogni tappa e' un oggetto")
        stato = t.get("stato", "futuro")
        if stato not in STATI_TAPPA:
            raise Errore(f"{d}.stato: dev'essere uno fra {sorted(STATI_TAPPA)}")
        if stato == "now":
            if visto_now:
                raise Errore(f"{dove}: due tappe marcate 'now', il pacco e' in un punto solo")
            visto_now = True
        elif stato == "done" and visto_now:
            raise Errore(f"{d}: tappa 'done' dopo la tappa corrente")
        tappe.append({
            "nome": testo(t.get("nome"), _campo(d, "nome"), 24),
            "data": testo(t.get("data"), _campo(d, "data"), 12, obbligatorio=False),
            "stato": stato,
        })
    if tappe[0]["stato"] == "futuro" and not visto_now:
        raise Errore(f"{dove}: nessuna tappa raggiunta, non e' un pacco aperto")
    return tappe


def meta(valore, dove):
    if not valore:
        return []
    if not isinstance(valore, list) or len(valore) > 4:
        raise Errore(f"{dove}: al massimo 4 voci di meta")
    out = []
    for i, m in enumerate(valore):
        d = _campo(dove, f"[{i}]")
        if not isinstance(m, dict):
            raise Errore(f"{d}: ogni meta e' un oggetto")
        out.append({
            "chiave": testo(m.get("chiave"), _campo(d, "chiave"), 20),
            "valore": testo(m.get("valore"), _campo(d, "valore"), 60),
        })
    return out


def azioni(valore, dove):
    if not valore:
        return []
    if not isinstance(valore, list) or len(valore) > 3:
        raise Errore(f"{dove}: al massimo 3 bottoni")
    out = []
    for i, a in enumerate(valore):
        d = _campo(dove, f"[{i}]")
        if not isinstance(a, dict):
            raise Errore(f"{d}: ogni azione e' un oggetto")
        out.append({
            "testo": testo(a.get("testo"), _campo(d, "testo"), 24),
            "url": url(a.get("url"), _campo(d, "url")),
            "nota": testo(a.get("nota"), _campo(d, "nota"), 40, obbligatorio=False),
        })
    return out


def voce(valore, dove):
    if not isinstance(valore, dict):
        raise Errore(f"{dove}: ogni voce e' un oggetto")
    tipo = valore.get("tipo", "riga")
    if tipo not in {"riga", "soldi"}:
        raise Errore(f"{dove}.tipo: dev'essere 'riga' o 'soldi'")
    base = {
        "tipo": tipo,
        "threadId": thread(valore.get("threadId"), _campo(dove, "threadId")),
        "urgente": bool(valore.get("urgente", False)),
    }
    if tipo == "soldi":
        importo = valore.get("importo") or {}
        if importo.get("stile") not in STILI_IMPORTO:
            raise Errore(f"{dove}.importo.stile: dev'essere uno fra {sorted(STILI_IMPORTO)}")
        base["importo"] = {
            "valore": testo(importo.get("valore"), _campo(dove, "importo.valore"), 16),
            "stile": importo["stile"],
        }
        base["chi"] = testo(valore.get("chi"), _campo(dove, "chi"), 80)
        base["testo"] = testo(valore.get("testo"), _campo(dove, "testo"), 200)
        return base
    base.update({
        "chi": testo(valore.get("chi"), _campo(dove, "chi"), 60),
        "testo": testo(valore.get("testo"), _campo(dove, "testo"), 500),
        "tag": tag(valore.get("tag"), _campo(dove, "tag")),
        "route": route(valore.get("route"), _campo(dove, "route")),
        "meta": meta(valore.get("meta"), _campo(dove, "meta")),
        "azioni": azioni(valore.get("azioni"), _campo(dove, "azioni")),
    })
    return base


def sezione(valore, nome):
    if valore is None:
        return None
    if not isinstance(valore, dict):
        raise Errore(f"sezioni.{nome}: dev'essere un oggetto")
    voci = valore.get("voci") or []
    if not isinstance(voci, list):
        raise Errore(f"sezioni.{nome}.voci: dev'essere una lista")
    if len(voci) > 12:
        raise Errore(f"sezioni.{nome}: troppe voci ({len(voci)}), massimo 12")
    if not voci:
        return None  # Una sezione vuota non va in pagina: sparisce e basta.
    return {
        "nota": testo(valore.get("nota"), f"sezioni.{nome}.nota", 60, obbligatorio=False),
        "coda": testo(valore.get("coda"), f"sezioni.{nome}.coda", 400, obbligatorio=False),
        "voci": [voce(v, f"sezioni.{nome}.voci[{i}]") for i, v in enumerate(voci)],
    }


def contatori(valore):
    if not isinstance(valore, list) or not 1 <= len(valore) <= 5:
        raise Errore("contatori: da 1 a 5 riquadri")
    out, urgenti = [], 0
    for i, c in enumerate(valore):
        d = f"contatori[{i}]"
        if not isinstance(c, dict):
            raise Errore(f"{d}: dev'essere un oggetto")
        urgente = bool(c.get("urgente", False))
        urgenti += urgente
        out.append({
            "n": intero(c.get("n"), _campo(d, "n")),
            "etichetta": testo(c.get("etichetta"), _campo(d, "etichetta"), 18),
            "urgente": urgente,
        })
    if urgenti > 1:
        raise Errore("contatori: un solo riquadro puo' essere urgente")
    return out


def rumore(valore):
    if valore is None:
        return None
    if not isinstance(valore, dict):
        raise Errore("rumore: dev'essere un oggetto")
    split = valore.get("split") or []
    if not isinstance(split, list) or len(split) > 4:
        raise Errore("rumore.split: al massimo 4 voci")
    voci = []
    for i, s in enumerate(split):
        d = f"rumore.split[{i}]"
        voci.append({
            "n": intero(s.get("n"), _campo(d, "n")),
            "etichetta": testo(s.get("etichetta"), _campo(d, "etichetta"), 18),
        })
    return {
        "totale": intero(valore.get("totale"), "rumore.totale"),
        "testo": testo(valore.get("testo"), "rumore.testo", 200),
        "split": voci,
    }


def valida(dati):
    """Trasforma il JSON grezzo nel modello pulito, o alza Errore.

    Tutto cio' che passa di qui e' gia' stato controllato campo per campo:
    il renderer non deve fidarsi di nient'altro.
    """
    if not isinstance(dati, dict):
        raise Errore("il file non contiene un oggetto JSON")

    data = dati.get("data") or {}
    if not ISO.match(str(data.get("oggi_iso", ""))):
        raise Errore("data.oggi_iso: serve una data ISO, es. 2026-09-21")
    if not STAMP.match(str(data.get("stamp", ""))):
        raise Errore("data.stamp: serve la forma GG.MM")

    titolo = dati.get("titolo") or {}
    frase = testo(titolo.get("testo"), "titolo.testo", 90)
    evidenzia = testo(titolo.get("evidenzia"), "titolo.evidenzia", 30, obbligatorio=False)
    if evidenzia and evidenzia not in frase:
        raise Errore("titolo.evidenzia: la parola da evidenziare non e' nella frase")

    sezioni = {}
    for nome, _ in SEZIONI:
        s = sezione((dati.get("sezioni") or {}).get(nome), nome)
        if s:
            sezioni[nome] = s

    pulito = {
        "data": {
            "oggi": testo(data.get("oggi"), "data.oggi", 24),
            "oggi_iso": data["oggi_iso"],
            "stamp": data["stamp"],
            "anno": data["oggi_iso"][:4],
        },
        "titolo": {"testo": frase, "evidenzia": evidenzia},
        "thread_letti": intero(dati.get("thread_letti"), "thread_letti", 0, 2000),
        "contatori": contatori(dati.get("contatori")),
        "sezioni": sezioni,
        "rumore": rumore(dati.get("rumore")),
        "footer": testo(dati.get("footer"), "footer", 300, obbligatorio=False),
        "serata_tranquilla": not sezioni,
    }

    # Coerenza: un contatore non puo' dichiarare piu' voci di quante ce ne siano.
    quante = {nome: len(s["voci"]) for nome, s in sezioni.items()}
    for c in pulito["contatori"]:
        if c["n"] > sum(quante.values()) + (pulito["rumore"]["totale"] if pulito["rumore"] else 0):
            raise Errore(f"contatori: {c['etichetta']} dichiara {c['n']}, piu' di tutto quello in pagina")
    return pulito
