# AuthentiPi

AuthentiPi is een zelf-gehoste, PiHole-achtige service voor je thuisnetwerk die
probeert te herkennen welk verkeer met AI-gegenereerde content te maken heeft,
en dat markeert in een dashboard — zonder de content zelf naar de cloud te
sturen.

Net als PiHole draait het als DNS-resolver in je netwerk en werkt het met
abonneerbare, updatebare lijsten. Waar PiHole domeinen blokkeert, markeert
AuthentiPi ze (en breidt dat in latere fases uit met echte content-herkenning
via de [C2PA](https://c2pa.org/) content-provenance standaard).

## Status

Vroege proof-of-concept. Fase 1 hieronder is de huidige scope.

## Architectuur (gefaseerd)

**Fase 1 — nu (DNS + domeinlijsten, geen decryptie nodig)**
- `dnsmasq` container die als netwerk-DNS-resolver draait en queries logt.
- Een Python-service (`app/`) die de dnsmasq-log tailt, domeinen matcht tegen
  een lijst van bekende AI-diensten (`rules/`), en treffers opslaat in SQLite.
- Web-dashboard (FastAPI + Jinja2/htmx) met:
  - overzicht van gedetecteerde AI-domeinbezoeken (per client, per dienst,
    per categorie, in de tijd)
  - instellingenpagina om categorieën aan/uit te zetten en geladen lijsten
    te bekijken

**Fase 2 — later (optioneel, geavanceerder)**
- Optionele MITM TLS-proxy modus (bijv. gebaseerd op mitmproxy) die
  afbeeldingen/video daadwerkelijk kan controleren op C2PA Content
  Credentials-metadata voor betrouwbaardere "dit is bevestigd
  AI-gegenereerd/bewerkt"-markeringen. Vereist het installeren van een eigen
  CA-certificaat op clients — expliciet opt-in.

**Fase 3 — experimenteel**
- Lokale detectie van AI-geschreven tekst in HTTP-responses. Nadrukkelijk
  als "experimenteel" gemarkeerd: tekstdetectie is technisch onbetrouwbaar
  (veel false positives/negatives).

## Lokaal draaien (testen, geen echte netwerk-DNS)

```bash
docker compose up --build
```

Dashboard: http://localhost:8080

Dit start standaard **niet** als DNS-server voor je hele netwerk — dat vereist
dat je de `dns`-service op poort 53 bereikbaar maakt voor andere apparaten en
je router/DHCP instelt om deze host als DNS-server te gebruiken. Zie
[`dns/README.md`](dns/) (volgt) voor die stap wanneer je het op een
Raspberry Pi als netwerk-brede resolver wilt draaien.

## Testen

### Automatische integratietests

`tests/` bevat pytest-integratietests die tegen een draaiende stack echte
DNS-queries doen en via de API checken of dat wel/niet tot een detectie
leidt. Nieuwe testgevallen toevoegen (bijv. voor een nieuwe dienst in
`rules/`) kan door `tests/test_detection.py` uit te breiden — de helpers in
`tests/helpers.py` (`dns_query`, `wait_for_new_detection`,
`set_category`, ...) zijn generiek herbruikbaar.

```bash
docker compose up -d
python3 -m venv .venv && source .venv/bin/activate
pip install -r tests/requirements-test.txt
pytest tests/ -v
```

Optioneel te overschrijven via env vars: `AUTHENTIPI_TEST_DNS_HOST` (default
`127.0.0.1`) en `AUTHENTIPI_TEST_API_BASE` (default `http://localhost:8080`)
— handig om dezelfde tests tegen een Raspberry Pi op je netwerk te draaien.

### Testen met een echt client-apparaat

1. Zoek het LAN-IP van de machine waar AuthentiPi op draait (op macOS:
   `ipconfig getifaddr en0`).
2. Zet op een ander apparaat (telefoon, laptop) de DNS-server handmatig op
   dat IP (bv. bij een iPhone: Wi-Fi-netwerk → Configureer DNS → Handmatig).
3. Open op dat apparaat een bekende AI-dienst uit `rules/default.yaml`
   (bv. chatgpt.com) en kijk of er een nieuwe rij verschijnt op het
   dashboard.

**Bekende beperking op macOS/Windows met Docker Desktop:** al het
binnenkomende verkeer naar gepubliceerde poorten wordt door Docker Desktop's
interne VM omgezet naar één gateway-adres (`192.168.65.1`), ongeacht welk
apparaat de query stuurde. Je ziet dus wél of iets herkend wordt, maar niet
betrouwbaar *van welk apparaat*. Op een Raspberry Pi (native Linux, geen
Docker Desktop-VM) werkt client-IP-herkenning wel correct.

## Domeinlijsten (`rules/`)

Zie [`rules/README.md`](rules/README.md) voor het formaat en hoe je eigen
lijsten toevoegt of abonneert op externe lijsten (net als PiHole-adlists).

## Licentie

MIT — zie [`LICENSE`](LICENSE).
