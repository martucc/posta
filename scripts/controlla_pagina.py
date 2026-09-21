"""Blocca la pubblicazione se nella pagina c'e un IBAN o un numero di carta completo.

La pagina e pubblica: e l'ultima difesa se Claude copia un dato che non doveva.
Esce con codice 1 e dice cosa ha trovato.
"""

import re
import sys


def luhn(digits):
    total = 0
    for i, d in enumerate(reversed(digits)):
        n = int(d)
        if i % 2:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
    return total % 10 == 0


def iban_valid(iban):
    """Checksum mod-97: esclude i tracking che per caso hanno la forma di un IBAN."""
    moved = iban[4:] + iban[:4]
    return int("".join(str(int(c, 36)) for c in moved)) % 97 == 1


def main(path):
    with open(path, encoding="utf-8") as f:
        page = f.read()
    body = page.split("</head>", 1)[-1].split("<script", 1)[0]
    text = re.sub(r"<[^>]+>", " ", body)
    problems = []
    for iban in re.findall(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]){11,30}\b", text):
        compact = iban.replace(" ", "")
        if iban_valid(compact):
            problems.append(f"IBAN che finisce con {compact[-4:]}")
    # Solo formati da carta: 4-4-4-4 separati, oppure 15-16 cifre di fila che iniziano
    # come Visa, Mastercard o Amex. I tracking numerici lunghi non devono bloccare.
    cards = re.findall(r"\b\d{4}[ -]\d{4}[ -]\d{4}[ -]\d{2,4}\b", text)
    cards += re.findall(r"\b[345]\d{14,15}\b", text)
    for card in cards:
        digits = re.sub(r"\D", "", card)
        if luhn(digits):
            problems.append(f"possibile numero di carta che finisce con {digits[-4:]}")
    if problems:
        print("; ".join(problems))
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1])
