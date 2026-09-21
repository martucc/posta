"""Costruisce index.html dal modello della serata, senza toccare il design.

Il file esistente e' il template: da lui prendiamo testa (fino a <body>) e coda
(dallo <script> finale in poi) e li riportiamo identici, byte per byte. In mezzo
rigeneriamo solo il contenuto, usando i componenti che gia' esistono nel CSS.
Nessuna sostituzione di stringhe a indovinare: due tagli netti e un corpo nuovo.
"""

import html
import json
import re
import sys

from dati import SEZIONI, valida

GRASSETTO = re.compile(r"\*\*(.+?)\*\*")
FRECCIA = ('<svg class="arrow" viewBox="0 0 16 16" fill="none" aria-hidden="true">'
           '<path d="M6 3l5 5-5 5" stroke="currentColor" stroke-width="2" '
           'stroke-linecap="round" stroke-linejoin="round"/></svg>')
ESTERNO = ('<svg viewBox="0 0 16 16" fill="none"><path d="M5 11l6-6M6 5h5v5" '
           'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
           'stroke-linejoin="round"/></svg>')
MAIL = "https://mail.google.com/mail/u/0/#all/"


def e(s):
    """Tutto il testo che viene dalle mail passa di qui: niente HTML dai dati."""
    return html.escape(s or "", quote=True)


def ricco(s):
    """Solo **grassetto** sopravvive, e diventa <strong>. Il resto e' testo."""
    return GRASSETTO.sub(r"<strong>\1</strong>", e(s))


def num(n):
    return f"{n:02d}" if n < 100 else str(n)


def testata(d):
    t = d["titolo"]
    frase = e(t["testo"])
    if t["evidenzia"]:
        frase = frase.replace(e(t["evidenzia"]), f'<span class="hl">{e(t["evidenzia"])}</span>', 1)
    def riquadro(c):
        urg = ' class="urg"' if c["urgente"] else ""
        return f'      <div{urg}><b>{c["n"]}</b><span>{e(c["etichetta"])}</span></div>'
    riquadri = "\n".join(riquadro(c) for c in d["contatori"])
    giorno, mese = d["data"]["stamp"], d["data"]["anno"]
    return f'''  <header class="head">
    <svg class="stamp" viewBox="0 0 120 120" fill="none" aria-hidden="true">
      <circle cx="60" cy="60" r="54" stroke="currentColor" stroke-width="2.5"/>
      <circle cx="60" cy="60" r="44" stroke="currentColor" stroke-width="1" stroke-dasharray="3 4"/>
      <text x="60" y="47" text-anchor="middle" fill="currentColor"
            style="font:700 12px/1 'JetBrains Mono',monospace;letter-spacing:.22em">LUGO</text>
      <text x="60" y="68" text-anchor="middle" fill="currentColor"
            style="font:700 15px/1 'JetBrains Mono',monospace;letter-spacing:.04em">{giorno}</text>
      <text x="60" y="83" text-anchor="middle" fill="currentColor"
            style="font:400 9px/1 'JetBrains Mono',monospace;letter-spacing:.2em">{mese} · RA</text>
      <path d="M18 98c8-6 16-6 24 0s16 6 24 0 16-6 24 0" stroke="currentColor" stroke-width="2"/>
    </svg>

    <div class="brandline">
      <svg class="mark" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <rect x="2.4" y="5.6" width="19.2" height="12.8" rx="2" stroke="currentColor" stroke-width="2"/>
        <path d="M3.8 6.9L12 13.2l8.2-6.3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      <span class="brand">Posta della sera</span>
      <button class="install" id="install" type="button">Installa</button>
    </div>

    <h1>{frase}</h1>
    <p class="dateline"><b>{e(d["data"]["oggi"])}</b> · ultime 24 ore · {d["thread_letti"]} thread letti</p>

    <div class="board">
{riquadri}
    </div>
  </header>'''


def timeline(tappe):
    righe = []
    for t in tappe:
        classe = f' class="{t["stato"]}"' if t["stato"] in ("done", "now") else ""
        data = f'<em>{e(t["data"])}</em>' if t["data"] else ""
        righe.append(f'              <li{classe}><b>{e(t["nome"])}</b>{data}</li>')
    return '            <ol class="route">\n' + "\n".join(righe) + "\n            </ol>"


def piede(azioni):
    if not azioni:
        return ""
    parti = []
    for a in azioni:
        if a["nota"]:
            parti.append(f'            <span class="hint">{e(a["nota"])}</span>')
        parti.append(
            f'            <a class="btn" href="{e(a["url"])}" target="_blank" rel="noopener">\n'
            f'              {e(a["testo"])}{ESTERNO}</a>')
    return '\n          <div class="foot">\n' + "\n".join(parti) + "\n          </div>"


def scheda(v):
    link = f'{MAIL}{v["threadId"]}'
    if v["tipo"] == "soldi":
        return f'''        <div class="card">
          <a class="cash" href="{link}" target="_blank" rel="noopener">
            <span class="amt {v["importo"]["stile"]}">{e(v["importo"]["valore"])}</span>
            <span class="cash-txt"><b>{e(v["chi"])}</b>
              <span>{e(v["testo"])}</span></span>
          </a>
        </div>'''
    classe = "card urgent" if v["urgente"] else "card"
    tag = f'<span class="tag {v["tag"]["stile"]}">{e(v["tag"]["testo"])}</span>' if v["tag"] else ""
    pezzi = [f'            <div class="row-top"><span class="who">{e(v["chi"])}</span>{tag}</div>',
             f'            <p>{ricco(v["testo"])}</p>']
    if v["route"]:
        pezzi.append(timeline(v["route"]))
    if v["meta"]:
        celle = "".join(f'<span><i>{e(m["chiave"])}</i> <code>{e(m["valore"])}</code></span>'
                        for m in v["meta"])
        pezzi.append(f'            <div class="meta">{celle}</div>')
    corpo = "\n".join(pezzi)
    return f'''        <div class="{classe}">
          <a class="row" href="{link}" target="_blank" rel="noopener">
            {FRECCIA}
{corpo}
          </a>{piede(v["azioni"])}
        </div>'''


def sezione(nome, titolo, s):
    nota = f'\n        <span class="note">{e(s["nota"])}</span>' if s["nota"] else ""
    schede = "\n\n".join(scheda(v) for v in s["voci"])
    coda = f'\n      <div class="quiet">{ricco(s["coda"])}</div>' if s["coda"] else ""
    return f'''    <section>
      <div class="sec-head"><h2>{titolo}</h2><span class="n">{num(len(s["voci"]))}</span>\
<span class="rule"></span>{nota}</div>
      <div class="rows">

{schede}

      </div>{coda}
    </section>'''


def sezione_rumore(r):
    split = "".join(f'<span><i>{s["n"]}</i> {e(s["etichetta"])}</span>' for s in r["split"])
    blocco = f'\n        <div class="split">{split}</div>' if split else ""
    return f'''    <section>
      <div class="sec-head"><h2>Rumore</h2><span class="n">{num(r["totale"])}</span>\
<span class="rule"></span></div>
      <div class="quiet">
        {e(r["testo"])}{blocco}
      </div>
    </section>'''


def serata_tranquilla(d):
    return '''    <section>
      <div class="sec-head"><h2>Serata tranquilla</h2><span class="rule"></span></div>
      <div class="quiet">Niente che richieda la tua attenzione: nessun pacco aperto,
        nessuna scadenza, nessun movimento.</div>
    </section>'''


def corpo(d):
    parti = [testata(d), '  <div class="perf"></div>', '  <div class="stack">', ""]
    if d["serata_tranquilla"]:
        parti.append(serata_tranquilla(d))
    else:
        for nome, titolo in SEZIONI:
            if nome in d["sezioni"]:
                parti.append(sezione(nome, titolo, d["sezioni"][nome]))
                parti.append("")
        parti.pop()
    if d["rumore"]:
        parti += ["", sezione_rumore(d["rumore"])]
    parti.append("")
    parti.append("  </div>")
    if d["footer"]:
        parti += ["", f'  <footer>\n    {ricco(d["footer"])}<br>\n'
                      '    Ogni riquadro apre la mail da cui viene.\n  </footer>']
    return "\n".join(parti)


def taglia(pagina):
    """Testa e coda del template esistente. Se il file non ha la forma attesa,
    meglio fermarsi che pubblicare una pagina mutilata."""
    fine_head = pagina.find("</head>")
    apre_body = pagina.find("<body>", fine_head)
    ultimo_script = pagina.rfind("<script>")
    if fine_head < 0 or apre_body < 0 or ultimo_script < apre_body:
        raise ValueError("index.html non ha la struttura attesa: </head>, <body>, <script> finale")
    return pagina[:apre_body + len("<body>")], pagina[ultimo_script:]


def rendi(template, dati):
    testa, coda = taglia(template)
    d = valida(dati)
    return f'{testa}\n<div class="page">\n\n{corpo(d)}\n\n</div>\n\n{coda}'


def main(percorso_pagina, percorso_dati, destinazione):
    with open(percorso_pagina, encoding="utf-8") as f:
        template = f.read()
    with open(percorso_dati, encoding="utf-8") as f:
        dati = json.load(f)
    nuova = rendi(template, dati)
    with open(destinazione, "w", encoding="utf-8") as f:
        f.write(nuova)
    print(f"pagina rigenerata: {len(nuova)} caratteri")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else sys.argv[1])
