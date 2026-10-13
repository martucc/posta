"""Dice perche' claude-code-action si e' fermato, senza mostrare la posta.

L'action nasconde il suo output per sicurezza, e fa bene: dentro c'e' la posta
di Martucc e i log di un repo pubblico sono pubblici. Ma cosi' il 4 e il 10
ottobre si e' visto solo "is_error: true" dopo 439 ms, senza sapere se era il
token, un limite d'uso o il modello. Da qui esce solo il motivo:

  - se Claude non ha fatto nemmeno un giro completo (costo zero o un turno),
    il testo del risultato e' l'errore dell'API, non posta: lo mostriamo,
    accorciato e ripulito da qualsiasi cosa somigli a un token;
  - altrimenti diciamo solo tipo di fine e numero di turni.

Non fallisce mai: e' diagnostica, non deve fermare il resto della serata.
Uso: perche_claude.py <execution_file> <file_di_uscita>
"""

import json
import re
import sys

MAX = 220
SEGRETI = re.compile(r"(sk-ant-[A-Za-z0-9_-]+|[A-Za-z0-9_-]{32,}|Bearer\s+\S+)", re.I)


def messaggi(percorso):
    try:
        with open(percorso, encoding="utf-8") as f:
            grezzo = f.read()
    except OSError:
        return []
    try:
        dati = json.loads(grezzo)
        return dati if isinstance(dati, list) else [dati]
    except ValueError:
        out = []
        for riga in grezzo.splitlines():
            try:
                out.append(json.loads(riga))
            except ValueError:
                continue
        return out


def pulisci(testo):
    testo = re.sub(r"\s+", " ", str(testo or "")).strip()
    testo = SEGRETI.sub("[…]", testo)
    return testo[:MAX] + ("…" if len(testo) > MAX else "")


def motivo(lista):
    risultato = next((m for m in reversed(lista)
                      if isinstance(m, dict) and m.get("type") == "result"), None)
    if risultato is None:
        return "Claude non ha prodotto un risultato (nessun file di esecuzione leggibile)"
    turni = risultato.get("num_turns")
    tipo = risultato.get("subtype", "?")
    costo = risultato.get("total_cost_usd")
    partito = not (costo == 0 or (isinstance(turni, int) and turni <= 1))
    if partito:
        return f"Claude si e' fermato dopo {turni} turni ({tipo})"
    # Non e' partito: quello che c'e' e' l'errore dell'API.
    errori = [pulisci(m.get("error")) for m in lista
              if isinstance(m, dict) and isinstance(m.get("error"), str)]
    testo = pulisci(risultato.get("result"))
    stato = risultato.get("api_error_status")
    dettagli = "; ".join(x for x in [f"HTTP {stato}" if stato else "", *errori, testo] if x)
    return "Claude non e' partito: " + (dettagli or f"errore senza messaggio ({tipo})")


def main(percorso, uscita):
    try:
        riga = motivo(messaggi(percorso))
    except Exception as errore:  # la diagnostica non deve mai rompere la serata
        riga = f"Claude si e' fermato, motivo illeggibile ({type(errore).__name__})"
    print(riga)
    try:
        with open(uscita, "w", encoding="utf-8") as f:
            f.write(riga + "\n")
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "",
                  sys.argv[2] if len(sys.argv) > 2 else "/dev/null"))
