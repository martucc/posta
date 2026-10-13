"""Decide se questa corsa e' quella buona, e per quale serata.

GitHub consegna i cron anche con ore di ritardo: il 12 ottobre le due corse
delle 20 e delle 21 sono arrivate alle 2:06 e alle 3:03 di notte, la vecchia
guardia ha letto "sono le 2, non e' ancora sera" e la pagina e' rimasta ferma.
Una corsa fra mezzanotte e le 6 e' ancora la serata di ieri: si pubblica, con
la data di ieri, cosi' la corsa di stasera non la scambia per gia' fatta.

Scrive in $GITHUB_OUTPUT: esegui (si/no), serata (AAAA-MM-GG), etichetta
(GG.MM.AAAA, quella del commit "Riepilogo del ...").
"""

import os
import subprocess
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

INIZIO_SERA = 20   # da quest'ora parte la serata di oggi
FINE_NOTTE = 6     # fino a quest'ora il cron vale ancora per la serata di ieri


def serata_di(adesso):
    """Prima delle 20 la serata di oggi non e' ancora cominciata: qualunque
    corsa, anche a mano alle 15, lavora sulla serata di ieri. Se prendesse la
    data di oggi, le corse vere di stasera la troverebbero gia' pubblicata."""
    if adesso.hour < INIZIO_SERA:
        return (adesso - timedelta(days=1)).date()
    return adesso.date()


def decidi(adesso, evento, forza, pubblicate):
    """-> (giorno, etichetta, esegui, motivo). `pubblicate` sono gli oggetti
    degli ultimi commit di main."""
    giorno = serata_di(adesso)
    etichetta = giorno.strftime("%d.%m.%Y")
    if evento == "schedule" and FINE_NOTTE <= adesso.hour < INIZIO_SERA:
        return giorno, etichetta, False, (
            f"a Roma sono le {adesso:%H:%M}: troppo tardi per ieri sera, "
            "troppo presto per stasera")
    if not forza and f"Riepilogo del {etichetta}" in pubblicate:
        return giorno, etichetta, False, f"la serata del {etichetta} e' gia' pubblicata"
    return giorno, etichetta, True, f"si parte: serata del {etichetta}, a Roma sono le {adesso:%H:%M}"


def oggetti_recenti(quanti=60):
    try:
        uscita = subprocess.run(["git", "log", f"-n{quanti}", "--format=%s"],
                                capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as errore:
        print(f"non riesco a leggere la storia di git ({errore}): la tratto come vuota")
        return set()
    return {riga.strip() for riga in uscita.splitlines()}


def main():
    adesso = datetime.now(ZoneInfo(os.environ.get("TIMEZONE", "Europe/Rome")))
    evento = os.environ.get("EVENTO", "")
    forza = os.environ.get("FORZA", "").strip().lower() == "true"
    giorno, etichetta, esegui, motivo = decidi(adesso, evento, forza, oggetti_recenti())
    print(motivo if esegui else f"salto: {motivo}")
    uscite = os.environ.get("GITHUB_OUTPUT")
    righe = [f"esegui={'si' if esegui else 'no'}", f"serata={giorno.isoformat()}",
             f"etichetta={etichetta}"]
    if uscite:
        with open(uscite, "a", encoding="utf-8") as f:
            f.write("\n".join(righe) + "\n")
    else:
        print("\n".join(righe))


if __name__ == "__main__":
    sys.exit(main())
