"""Test della Posta della sera. Coprono le dieci cose che possono fare danno."""

import json
from pathlib import Path

import pytest

import applica
import controlla_pagina
import dati
import gmail
import rendi

RADICE = Path(__file__).resolve().parents[1]
TEMPLATE = (RADICE / "index.html").read_text(encoding="utf-8")
ESEMPIO = json.loads((RADICE / "tests/dati/giornata_esempio.json").read_text(encoding="utf-8"))


def msg(mid, **extra):
    base = {"messageId": mid, "threadId": "t" + mid, "labelIds": ["INBOX"],
            "etichette": [], "recente": True, "in_inbox": True,
            "fromAddress": "negozio@example.com", "subject": "oggetto", "snippet": ""}
    base.update(extra)
    return base


def posta(recenti=(), vecchi=(), pacchi=()):
    return {
        "oggi_iso": "2026-09-21",
        "ultime_24h": [{"threadId": "t1", "messages": list(recenti) + list(vecchi)}],
        "pacchi": [{"threadId": "t2", "messages": list(pacchi)}],
    }


# ─────────── 1. classificazione: solo etichette vere, solo messaggi veri ───────────

def test_etichetta_sconosciuta_viene_scartata():
    m = msg("a")
    scelte = applica.etichette_da_applicare(
        {"etichette": [{"messageId": "a", "etichetta": "Inventata"}]},
        {"a": m}, {"a"}, {"Promo": "Label_52"})
    assert scelte == {}


def test_etichetta_su_messaggio_non_scaricato_viene_scartata():
    """Una mail puo' scrivere un messageId qualsiasi: non deve bastare."""
    scelte = applica.etichette_da_applicare(
        {"etichette": [{"messageId": "sconosciuto", "etichetta": "Promo"}]},
        {}, set(), {"Promo": "Label_52"})
    assert scelte == {}


def test_etichetta_gia_presente_non_viene_riproposta():
    m = msg("a", etichette=["Promo"])
    scelte = applica.etichette_da_applicare(
        {"etichette": [{"messageId": "a", "etichetta": "Promo"}]},
        {"a": m}, {"a"}, {"Promo": "Label_52"})
    assert scelte == {}


# ─────────── 2. cestino: solo il mittente, mai la parola nel corpo ───────────

def test_nel_cestino_solo_il_mittente_configurato():
    assert "dan@tldrnewsletter.com" in gmail.CESTINO


def test_la_parola_tldr_nel_corpo_non_basta():
    m = msg("a", fromAddress="amica@example.com", snippet="ecco il TLDR della riunione")
    assert m["fromAddress"] not in gmail.CESTINO


# ─────────── 3. archiviazione ───────────

def test_di_default_non_archivia_niente():
    """Scelta di Martucc: le mail vengono etichettate e basta, restano in inbox."""
    m = msg("a", etichette=["Promo/Moda"])
    assert applica.ARCHIVIA is False
    assert applica.decidi_archivio("a", {"a": m}, {}) is False


def test_archivia_il_rumore_se_acceso(monkeypatch):
    monkeypatch.setattr(applica, "ARCHIVIA", True)
    m = msg("a", etichette=["Promo/Moda"])
    assert applica.decidi_archivio("a", {"a": m}, {}) is True


def test_non_archivia_se_dentro_c_e_un_ordine(monkeypatch):
    """Promo + conferma d'ordine: resta in inbox anche ad archiviazione accesa."""
    monkeypatch.setattr(applica, "ARCHIVIA", True)
    m = msg("a", etichette=["Promo", "Ordini/Confermati"])
    assert applica.decidi_archivio("a", {"a": m}, {}) is False


def test_non_archivia_quello_che_non_e_in_inbox(monkeypatch):
    monkeypatch.setattr(applica, "ARCHIVIA", True)
    m = msg("a", etichette=["Promo"], in_inbox=False, labelIds=[])
    assert applica.decidi_archivio("a", {"a": m}, {}) is False


def test_archivia_anche_con_etichetta_appena_proposta(monkeypatch):
    monkeypatch.setattr(applica, "ARCHIVIA", True)
    m = msg("a")
    assert applica.decidi_archivio("a", {"a": m}, {"a": {"Social"}}) is True


# ─────────── 4 e 5. ordini, timeline, pacchi chiusi ───────────

def test_timeline_vuole_quattro_tappe():
    with pytest.raises(dati.Errore, match="quattro|4 tappe|esattamente"):
        dati.route([{"nome": "Ordinato", "stato": "done"}], "v.route")


def test_timeline_non_ammette_due_tappe_correnti():
    tappe = [{"nome": "a", "stato": "now"}, {"nome": "b", "stato": "now"},
             {"nome": "c", "stato": "futuro"}, {"nome": "d", "stato": "futuro"}]
    with pytest.raises(dati.Errore, match="due tappe"):
        dati.route(tappe, "v.route")


def test_timeline_non_ammette_una_tappa_fatta_dopo_quella_corrente():
    tappe = [{"nome": "a", "stato": "now"}, {"nome": "b", "stato": "done"},
             {"nome": "c", "stato": "futuro"}, {"nome": "d", "stato": "futuro"}]
    with pytest.raises(dati.Errore, match="dopo la tappa corrente"):
        dati.route(tappe, "v.route")


def test_un_pacco_senza_nessuna_tappa_raggiunta_non_e_aperto():
    tappe = [{"nome": n, "stato": "futuro"} for n in "abcd"]
    with pytest.raises(dati.Errore, match="non e' un pacco aperto"):
        dati.route(tappe, "v.route")


# ─────────── 6. il design non si tocca ───────────

def test_testa_e_coda_restano_identiche():
    nuova = rendi.rendi(TEMPLATE, ESEMPIO)
    for pagina in (TEMPLATE, nuova):
        assert "</head>" in pagina and "<script>" in pagina
    assert TEMPLATE[:TEMPLATE.find("<body>")] == nuova[:nuova.find("<body>")]
    assert TEMPLATE[TEMPLATE.rfind("<script>"):] == nuova[nuova.rfind("<script>"):]


def test_la_pagina_generata_passa_il_controllo():
    nuova = rendi.rendi(TEMPLATE, ESEMPIO)
    assert controlla_pagina.controlla(nuova, TEMPLATE) == []


def test_il_controllo_si_accorge_se_sparisce_il_service_worker():
    nuova = rendi.rendi(TEMPLATE, ESEMPIO).replace("serviceWorker.register", "niente")
    problemi = controlla_pagina.controlla(nuova, TEMPLATE)
    assert any("service worker" in p for p in problemi)


def test_il_controllo_si_accorge_se_cambia_il_css():
    rotta = TEMPLATE.replace("--orange:#FF5A2B", "--orange:#00FF00")
    nuova = rendi.rendi(rotta, ESEMPIO)
    problemi = controlla_pagina.controlla(nuova, TEMPLATE)
    assert any("testa della pagina" in p for p in problemi)


def test_il_controllo_rifiuta_le_sezioni_fuori_ordine():
    nuova = rendi.rendi(TEMPLATE, ESEMPIO)
    rotta = nuova.replace("<h2>Pacchi</h2>", "<h2>Progetti</h2>", 1)
    problemi = controlla_pagina.controlla(rotta, TEMPLATE)
    assert any("fuori ordine" in p for p in problemi)


def test_il_controllo_rifiuta_un_contatore_che_mente():
    nuova = rendi.rendi(TEMPLATE, ESEMPIO)
    rotta = nuova.replace('<h2>Pacchi</h2><span class="n">02</span>',
                          '<h2>Pacchi</h2><span class="n">07</span>')
    problemi = controlla_pagina.controlla(rotta, TEMPLATE)
    assert any("il contatore dice 7" in p for p in problemi)


# ─────────── 7. validazione dei dati ───────────

def test_niente_html_dalle_mail():
    """Un oggetto con dentro del markup non deve diventare markup."""
    d = json.loads(json.dumps(ESEMPIO))
    d["sezioni"]["da_fare"]["voci"][0]["chi"] = '<img src=x onerror=alert(1)>'
    nuova = rendi.rendi(TEMPLATE, d)
    assert "<img" not in nuova          # non e' diventato un tag
    assert "&lt;img src=x" in nuova     # e' rimasto testo, visibile e innocuo


def test_il_titolo_da_evidenziare_deve_esistere_nella_frase():
    d = json.loads(json.dumps(ESEMPIO))
    d["titolo"]["evidenzia"] = "parola assente"
    with pytest.raises(dati.Errore, match="non e' nella frase"):
        dati.valida(d)


def test_una_parola_vietata_blocca_i_dati():
    d = json.loads(json.dumps(ESEMPIO))
    d["sezioni"]["da_fare"]["voci"][0]["testo"] = "il tuo codice OTP e' 448213"
    with pytest.raises(dati.Errore, match="vietata"):
        dati.valida(d)


def test_parlare_di_un_token_non_e_un_segreto():
    """Il falso positivo che ha bloccato la pagina il 21 settembre: la parola
    nuda non e' un segreto, lo e' il valore. Il controllo vero sta sulla forma,
    in controlla_pagina.py."""
    innocue = [
        "Il token del workflow e' scaduto, va rigenerato.",
        "Ritiro al Fermopoint, ti mandano il PIN per SMS.",
        "Rimborso accreditato sull'IBAN abituale.",
        "Cambia la password quando puoi.",
    ]
    for frase in innocue:
        d = json.loads(json.dumps(ESEMPIO))
        d["sezioni"]["da_fare"]["voci"][0]["testo"] = frase
        dati.valida(d)  # non deve alzare


def test_un_segreto_vero_blocca_ancora():
    for frase in ("password: hunter2extra",
                  "token ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                  "IBAN IT60X0542811101000000123456",
                  "Authorization: Bearer abcdefghijklmnop123"):
        d = json.loads(json.dumps(ESEMPIO))
        d["sezioni"]["da_fare"]["voci"][0]["testo"] = frase
        with pytest.raises(dati.Errore, match="vietata"):
            dati.valida(d)


def test_troppe_categorie_di_rumore_non_buttano_la_pagina():
    """Il caso del 23 settembre: sei categorie di rumore e il validatore
    rifiutava la pagina intera. Ora le ultime diventano 'Altro' e i conti tornano."""
    d = json.loads(json.dumps(ESEMPIO))
    categorie = [("Promo", 30), ("Promo/Moda", 12), ("Social", 8),
                 ("Promo/Sport", 5), ("Newsletter", 3), ("Scommesse", 1)]
    d["rumore"]["split"] = [{"n": n, "etichetta": e} for e, n in categorie]
    d["rumore"]["totale"] = sum(n for _, n in categorie)
    pulito = dati.valida(d)
    split = pulito["rumore"]["split"]
    assert len(split) == 4
    assert split[-1] == {"n": 9, "etichetta": "Altro"}
    assert sum(v["n"] for v in split) == d["rumore"]["totale"]
    assert controlla_pagina.controlla(rendi.rendi(TEMPLATE, d), TEMPLATE) == []


def test_troppi_bottoni_si_tagliano_non_si_rifiutano():
    d = json.loads(json.dumps(ESEMPIO))
    d["sezioni"]["pacchi"]["voci"][0]["azioni"] = [
        {"testo": f"Link {i}", "url": f"https://example.com/{i}"} for i in range(6)]
    pulito = dati.valida(d)
    assert len(pulito["sezioni"]["pacchi"]["voci"][0]["azioni"]) == 3


def test_la_sicurezza_invece_rifiuta_ancora():
    """Tagliare vale per l'estetica, non per la verita' o i segreti."""
    d = json.loads(json.dumps(ESEMPIO))
    d["sezioni"]["pacchi"]["voci"][0]["azioni"] = [{"testo": "X", "url": "javascript:alert(1)"}]
    with pytest.raises(dati.Errore):
        dati.valida(d)


def test_una_sezione_vuota_sparisce():
    d = json.loads(json.dumps(ESEMPIO))
    d["sezioni"]["viaggi"] = {"voci": []}
    pulito = dati.valida(d)
    assert "viaggi" not in pulito["sezioni"]
    assert "<h2>Viaggi</h2>" not in rendi.rendi(TEMPLATE, d)


def test_serata_tranquilla_quando_non_c_e_niente():
    d = json.loads(json.dumps(ESEMPIO))
    d["sezioni"] = {}
    d["contatori"] = [{"n": 44, "etichetta": "Rumore"}]
    nuova = rendi.rendi(TEMPLATE, d)
    assert "Serata tranquilla" in nuova
    assert controlla_pagina.controlla(nuova, TEMPLATE) == []


def test_un_link_non_https_viene_rifiutato():
    with pytest.raises(dati.Errore, match="URL https"):
        dati.azioni([{"testo": "Traccia", "url": "javascript:alert(1)"}], "v.azioni")


# ─────────── 8 e 9. segreti in pagina, errori ───────────

def test_un_iban_in_pagina_blocca_la_pubblicazione():
    nuova = rendi.rendi(TEMPLATE, ESEMPIO).replace(
        "<p>Casco", "<p>IT60X0542811101000000123456 Casco")
    problemi = controlla_pagina.controlla(nuova, TEMPLATE)
    assert any("IBAN" in p for p in problemi)


def test_un_tracking_lungo_non_viene_scambiato_per_un_iban():
    assert controlla_pagina.controlla(rendi.rendi(TEMPLATE, ESEMPIO), TEMPLATE) == []


def test_una_carta_in_pagina_blocca_la_pubblicazione():
    nuova = rendi.rendi(TEMPLATE, ESEMPIO).replace("<p>Casco", "<p>4539 1488 0343 6467 Casco")
    assert any("carta" in p for p in controlla_pagina.controlla(nuova, TEMPLATE))


def test_un_token_github_in_pagina_blocca_la_pubblicazione():
    nuova = rendi.rendi(TEMPLATE, ESEMPIO).replace(
        "<p>Casco", "<p>ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa Casco")
    assert any("token GitHub" in p for p in controlla_pagina.controlla(nuova, TEMPLATE))


def test_un_template_rotto_non_produce_una_pagina_mutilata():
    with pytest.raises(ValueError, match="struttura attesa"):
        rendi.rendi("<html>senza body</html>", ESEMPIO)


def test_l_oggetto_dell_email_non_puo_iniettare_header():
    sporco = "Riepilogo\r\nBcc: altro@example.com"
    assert "\n" not in gmail.pulisci_oggetto(sporco)
    assert "\r" not in gmail.pulisci_oggetto(sporco)


def test_oggetto_vuoto_ha_un_ripiego():
    assert gmail.pulisci_oggetto("   ") == "Posta della sera"


# ─────────── 10. idempotenza ───────────

def test_un_messaggio_vecchio_dentro_un_thread_recente_non_si_tocca():
    """Il caso che fa piu' danno: un thread riaperto oggi con dentro una mail
    di tre settimane fa. Quella non e' della serata e non va ne' archiviata
    ne' cestinata."""
    recente = msg("nuovo")
    vecchio = msg("vecchio", recente=False, fromAddress="dan@tldrnewsletter.com")
    _, agibili = applica.indice(posta(recenti=[recente], vecchi=[vecchio]))
    assert agibili == {"nuovo"}


def test_un_messaggio_gia_nel_cestino_non_si_ricestina():
    m = msg("a", labelIds=["TRASH"])
    _, agibili = applica.indice(posta(recenti=[m]))
    assert agibili == set()


def test_i_messaggi_dei_pacchi_non_sono_agibili():
    """I thread dei 21 giorni servono a ricostruire lo stato, non a essere toccati."""
    messaggi, agibili = applica.indice(posta(pacchi=[msg("p")]))
    assert "p" in messaggi and "p" not in agibili


def test_rendere_due_volte_gli_stessi_dati_da_lo_stesso_html():
    assert rendi.rendi(TEMPLATE, ESEMPIO) == rendi.rendi(TEMPLATE, ESEMPIO)


def test_rendere_sulla_pagina_di_ieri_da_lo_stesso_html():
    """Il template e' la pagina di ieri: rigenerare non deve accumulare nulla."""
    prima = rendi.rendi(TEMPLATE, ESEMPIO)
    assert rendi.rendi(prima, ESEMPIO) == prima
