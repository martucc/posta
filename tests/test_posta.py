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


def test_un_testo_troppo_lungo_si_accorcia_non_butta_la_pagina():
    """Il caso del 2 e 3 ottobre: una riga di Soldi di 303 caratteri contro un
    massimo di 200, e la pagina restava quella di ieri."""
    d = json.loads(json.dumps(ESEMPIO))
    lungo = ("Addebito ricorrente del piano annuale rinnovato in automatico, con "
             "**conferma via mail** e ricevuta allegata. ") * 4
    d["sezioni"]["soldi"]["voci"][0]["testo"] = lungo
    d["sezioni"]["pacchi"]["coda"] = "Chiusi e quindi esclusi: " + "cover, siero, casco; " * 25
    pulito = dati.valida(d)
    testo = pulito["sezioni"]["soldi"]["voci"][0]["testo"]
    coda = pulito["sezioni"]["pacchi"]["coda"]
    assert len(testo) <= 200 and testo.endswith("…")
    assert len(coda) <= 400 and coda.endswith("…")
    assert controlla_pagina.controlla(rendi.rendi(TEMPLATE, d), TEMPLATE) == []


def test_il_taglio_non_lascia_un_grassetto_a_meta():
    corto = dati.accorcia("Rimborso **in arrivo entro sette giorni lavorativi** dal reso", 30)
    assert len(corto) <= 30 and corto.endswith("…")
    assert corto.count("**") % 2 == 0


def test_un_segreto_dopo_il_punto_di_taglio_blocca_ancora():
    """Tagliare non deve nascondere un segreto che stava in fondo al testo."""
    d = json.loads(json.dumps(ESEMPIO))
    d["sezioni"]["soldi"]["voci"][0]["testo"] = "x " * 150 + "password: hunter2extra"
    with pytest.raises(dati.Errore, match="vietata"):
        dati.valida(d)


def test_un_titolo_tagliato_perde_l_evidenziato_ma_esce():
    d = json.loads(json.dumps(ESEMPIO))
    d["titolo"] = {"testo": "Tre pacchi in viaggio e una lunga lista di cose da fare prima "
                            "di giovedì sera, compresa la fattura",
                   "evidenzia": "la fattura"}
    pulito = dati.valida(d)
    assert len(pulito["titolo"]["testo"]) <= 90
    assert pulito["titolo"]["evidenzia"] is None


def test_troppi_contatori_o_due_urgenti_non_buttano_la_pagina():
    d = json.loads(json.dumps(ESEMPIO))
    d["contatori"] = [{"n": 1, "etichetta": f"C{i}", "urgente": True} for i in range(7)]
    pulito = dati.valida(d)
    assert len(pulito["contatori"]) == 5
    assert [c["urgente"] for c in pulito["contatori"]] == [True, False, False, False, False]


def test_la_parola_otp_senza_codice_non_ferma_la_pagina():
    d = json.loads(json.dumps(ESEMPIO))
    d["sezioni"]["da_fare"]["voci"][0]["testo"] = (
        "Attiva il 2FA: al primo accesso ti arriva un codice OTP per SMS, "
        "poi un codice di verifica via mail.")
    assert controlla_pagina.controlla(rendi.rendi(TEMPLATE, d), TEMPLATE) == []


def test_un_codice_otp_in_pagina_blocca_ancora():
    nuova = rendi.rendi(TEMPLATE, ESEMPIO).replace("<p>Casco", "<p>codice OTP: 448213 Casco")
    assert any("OTP" in p for p in controlla_pagina.controlla(nuova, TEMPLATE))


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


# ─────────── 11. la serata: i cron di GitHub arrivano in ritardo ───────────

import guardia
import leggi_posta
from datetime import datetime
from zoneinfo import ZoneInfo

ROMA = ZoneInfo("Europe/Rome")


def ore(*args, **kw):
    return datetime(*args, tzinfo=ROMA, **kw)


def test_una_corsa_dopo_mezzanotte_pubblica_la_serata_di_ieri():
    """Il 12 ottobre: cron delle 20 consegnato alle 2:06, e la pagina non usciva."""
    giorno, etichetta, esegui, _ = guardia.decidi(ore(2026, 10, 13, 2, 6), "schedule", False, set())
    assert esegui and giorno.isoformat() == "2026-10-12" and etichetta == "12.10.2026"


def test_la_seconda_corsa_tardiva_non_ripubblica():
    _, _, esegui, motivo = guardia.decidi(ore(2026, 10, 13, 3, 3), "schedule", False,
                                          {"Riepilogo del 12.10.2026"})
    assert not esegui and "gia' pubblicata" in motivo


def test_la_corsa_di_stasera_non_vede_la_serata_di_ieri_come_sua():
    """Pubblicata alle 2 la serata del 12, alle 20:17 del 13 si riparte."""
    giorno, _, esegui, _ = guardia.decidi(ore(2026, 10, 13, 20, 17), "schedule", False,
                                          {"Riepilogo del 12.10.2026"})
    assert esegui and giorno.isoformat() == "2026-10-13"


def test_di_giorno_il_cron_non_parte():
    for ora in (6, 12, 19):
        _, _, esegui, _ = guardia.decidi(ore(2026, 10, 13, ora, 17), "schedule", False, set())
        assert not esegui


def test_a_mano_si_parte_a_qualsiasi_ora_e_prima_delle_20_vale_ieri():
    """Una corsa a mano alle 15 rifa' la serata di ieri: se prendesse la data di
    oggi, stasera tutte le corse del cron la troverebbero gia' pubblicata."""
    giorno, _, esegui, _ = guardia.decidi(ore(2026, 10, 13, 15, 0), "workflow_dispatch", False, set())
    assert esegui and giorno.isoformat() == "2026-10-12"
    giorno, _, _, _ = guardia.decidi(ore(2026, 10, 13, 20, 30), "workflow_dispatch", False, set())
    assert giorno.isoformat() == "2026-10-13"


def test_forza_ripubblica_anche_se_gia_fatta():
    _, _, esegui, _ = guardia.decidi(ore(2026, 10, 13, 21, 0), "workflow_dispatch", True,
                                     {"Riepilogo del 13.10.2026"})
    assert esegui


def test_la_serata_attraversa_l_anno_e_il_cambio_d_ora():
    giorno, etichetta, _, _ = guardia.decidi(ore(2027, 1, 1, 1, 0), "schedule", False, set())
    assert giorno.isoformat() == "2026-12-31" and etichetta == "31.12.2026"
    # 25 ottobre 2026: le 2:30 esistono due volte, la serata resta il 24
    giorno, _, esegui, _ = guardia.decidi(ore(2026, 10, 25, 2, 30, fold=1), "schedule", False, set())
    assert esegui and giorno.isoformat() == "2026-10-24"


def test_leggi_posta_usa_la_data_della_serata():
    adesso = ore(2026, 10, 13, 2, 6)
    assert leggi_posta.giorno_della_serata(adesso, "2026-10-12").isoformat() == "2026-10-12"
    assert leggi_posta.giorno_della_serata(adesso, "").isoformat() == "2026-10-13"
    assert leggi_posta.giorno_della_serata(adesso, None).isoformat() == "2026-10-13"


# ─────────── 12. perche' Claude si e' fermato, senza mostrare la posta ───────────

import perche_claude


def test_se_claude_non_parte_si_vede_l_errore(tmp_path):
    f = tmp_path / "esecuzione.json"
    f.write_text(json.dumps([
        {"type": "system", "subtype": "init"},
        {"type": "result", "subtype": "success", "is_error": True, "num_turns": 1,
         "total_cost_usd": 0, "result": "Claude AI usage limit reached|1791850200"}]))
    riga = perche_claude.motivo(perche_claude.messaggi(str(f)))
    assert "non e' partito" in riga and "usage limit" in riga


def test_se_claude_ha_lavorato_la_posta_non_finisce_nel_log(tmp_path):
    f = tmp_path / "esecuzione.json"
    f.write_text(json.dumps([{"type": "result", "subtype": "error_max_turns", "is_error": True,
                              "num_turns": 31, "total_cost_usd": 1.2,
                              "result": "Il pacco di Mario Rossi in via Roma 1 arriva domani"}]))
    riga = perche_claude.motivo(perche_claude.messaggi(str(f)))
    assert "31 turni" in riga and "Mario" not in riga


def test_un_token_nell_errore_non_finisce_nel_log(tmp_path):
    f = tmp_path / "esecuzione.json"
    f.write_text(json.dumps([{"type": "result", "is_error": True, "num_turns": 0,
                              "result": "API Error: 401 invalid sk-ant-oat01-abcdefghijklmnop"}]))
    assert "sk-ant" not in perche_claude.motivo(perche_claude.messaggi(str(f)))


def test_senza_file_di_esecuzione_non_si_rompe(tmp_path):
    uscita = tmp_path / "esito.txt"
    assert perche_claude.main(str(tmp_path / "manca.json"), str(uscita)) == 0
    assert "nessun file" in uscita.read_text()


def test_la_finestra_non_lascia_buchi_fra_corse_a_orari_diversi():
    """Il 12 alle 20:17, poi la serata del 13 alle 2:06 del 14: con 24 ore secche
    le mail del 12 fra le 20:17 e le 2:06 del 13 non le leggeva nessuno."""
    giorno = leggi_posta.giorno_della_serata(ore(2026, 10, 14, 2, 6), "2026-10-13")
    inizio = leggi_posta.inizio_finestra(ore(2026, 10, 14, 2, 6), giorno)
    assert inizio == ore(2026, 10, 12, 20, 0)
    # di sera, all'ora giusta, resta come prima: 24 ore
    sera = ore(2026, 10, 13, 20, 17)
    assert leggi_posta.inizio_finestra(sera, sera.date()) == ore(2026, 10, 12, 20, 0)


def test_la_query_copre_la_finestra():
    adesso = ore(2026, 10, 13, 20, 17)
    assert "newer_than:2d" in leggi_posta.query_recenti(adesso, ore(2026, 10, 12, 20, 0))
    pomeriggio = ore(2026, 10, 13, 19, 59)
    assert "newer_than:3d" in leggi_posta.query_recenti(pomeriggio, ore(2026, 10, 11, 20, 0))


# ─────────── 13. l'avviso di fallimento non si mangia il riepilogo vero ───────────

def test_un_fallimento_non_blocca_il_riepilogo_della_corsa_dopo():
    marcatore, cerca = applica.marcatori("Riepilogo non generato: ...", "")
    assert marcatore == applica.MARCATORE_KO and applica.MARCATORE in cerca
    marcatore, cerca = applica.marcatori("", "pubblicata")
    assert marcatore == applica.MARCATORE and cerca == [applica.MARCATORE]
    # pagina online ma deploy lento: e' comunque il riepilogo vero
    marcatore, _ = applica.marcatori("Commit fatto, deploy non ancora confermato", "pubblicata")
    assert marcatore == applica.MARCATORE


def test_i_due_marcatori_si_cercano_insieme(monkeypatch):
    viste = []

    class Lista:
        def __init__(self, q): self.q = q
        def execute(self): viste.append(self.q); return {}

    class Servizio:
        def users(self): return self
        def messages(self): return self
        def list(self, userId, q, maxResults): return Lista(q)

    assert applica.gia_mandata(Servizio(), "2026-10-13",
                               [applica.MARCATORE, applica.MARCATORE_KO]) is False
    assert '"posta-della-sera:2026-10-13" OR "posta-della-sera-ko:2026-10-13"' in viste[0]


# ─────────── 14. segreti e taglio ───────────

def test_un_iban_a_gruppi_tagliato_a_meta_non_passa():
    d = json.loads(json.dumps(ESEMPIO))
    d["sezioni"]["soldi"]["voci"][0]["testo"] = (
        "Bonifico ricevuto per il rimborso del deposito cauzionale dell'appartamento, "
        "accreditato oggi sul conto con coordinate IT60 X054 2811 1010 0000 0123 456 "
        "come da accordi presi la settimana scorsa con l'agenzia")
    with pytest.raises(dati.Errore, match="vietata"):
        dati.valida(d)


def test_un_token_ricomposto_dal_taglio_non_passa():
    with pytest.raises(dati.Errore, match="vietata"):
        dati.testo("ghp_abcdefghij**klmnopqrstuvwxyz " + "riempitivo " * 30, "x", 100)


def test_un_tracking_con_la_forma_di_un_iban_non_e_un_segreto():
    for codice in ("LP00612345678901", "YT2312345678901234", "UB123456789012345"):
        assert dati.testo(codice, "meta.valore", 60) == codice


def test_un_token_anthropic_non_passa():
    with pytest.raises(dati.Errore, match="vietata"):
        dati.testo("sk-ant-oat01-" + "a" * 40, "x", 500)


def test_il_taglio_fra_gli_asterischi_non_lascia_un_asterisco():
    corto = dati.accorcia("Pagamento **entrovenerdìassolutamente** ok fine della frase lunga", 39)
    assert "*" not in corto


def test_i_codici_otp_scritti_a_gruppi_bloccano_la_pagina():
    for frase in ("Amazon: codice di verifica 448 213, scade fra 10 minuti",
                  "Il tuo OTP: 448-213",
                  "Codice OTP per il login:\n448213"):
        nuova = rendi.rendi(TEMPLATE, ESEMPIO).replace("<p>Casco", f"<p>{frase} Casco")
        assert any("OTP" in p for p in controlla_pagina.controlla(nuova, TEMPLATE)), frase


def test_una_data_dopo_la_parola_otp_non_blocca_la_pagina():
    d = json.loads(json.dumps(ESEMPIO))
    d["sezioni"]["da_fare"]["voci"][0]["testo"] = "Ti arriva un OTP per SMS al ritiro, entro il 15.10.2026"
    assert controlla_pagina.controlla(rendi.rendi(TEMPLATE, d), TEMPLATE) == []


def test_la_diagnosi_legge_gli_errori_della_cli_e_li_mette_nell_output(tmp_path):
    f = tmp_path / "esecuzione.json"
    f.write_text(json.dumps([{"type": "result", "subtype": "error_during_execution",
                              "is_error": True, "num_turns": 0, "total_cost_usd": 0,
                              "errors": ["OAuth token has expired"]}]))
    uscita = tmp_path / "output"
    perche_claude.main(str(f), str(uscita))
    assert uscita.read_text().startswith("motivo=Claude non e' partito: OAuth token has expired")
