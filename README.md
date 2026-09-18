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

Vroege proof-of-concept. Fase 1 en Fase 2 hieronder zijn gebouwd en getest.

## Architectuur (gefaseerd)

**Fase 1 — DNS + domeinlijsten (geen decryptie nodig)**
- `dnsmasq` container die als netwerk-DNS-resolver draait en queries logt.
- Een Python-service (`app/`) die de dnsmasq-log tailt, domeinen matcht tegen
  een lijst van bekende AI-diensten (`rules/`), en treffers opslaat in SQLite.
- Web-dashboard (FastAPI + Jinja2/htmx) met:
  - overzicht van gedetecteerde AI-domeinbezoeken (per client, per dienst,
    per categorie, in de tijd)
  - instellingenpagina om categorieën aan/uit te zetten en geladen lijsten
    te bekijken

**Fase 2 — content-marking via MITM-proxy (opt-in, expliciet meer invasief)**
- `proxy`-service (mitmproxy) die als HTTP(S)-proxy draait: onderschept
  afbeeldingen en controleert ze op [C2PA](https://c2pa.org/) Content
  Credentials-manifesten (via `c2pa-python`), en injecteert een klein
  script (`marker.js`) in HTML-pagina's.
- `marker.js` draait in de browser van de client, vraagt aan de backend
  welke afbeeldingen op de pagina een manifest hebben, en overlayt daar een
  badge op — de gebruiker ziet dus direct op de afbeelding zelf een
  markering, in plaats van alleen een dashboard-regel.
- Vereist het installeren van mitmproxy's CA-certificaat op clientapparaten
  (net als bedrijfs-firewalls doen) en het instellen van een HTTP-proxy op
  die apparaten. Zie "Content-marking testen" hieronder.
- **Belangrijke kanttekening over dekking:** C2PA is een nog groeiende
  standaard. Niet elke AI-afbeelding bevat een manifest (bijv. veel lokaal
  gedraaide Stable Diffusion-varianten doen dat niet), dus verwacht geen
  100%-dekking — dit is "als het er is, tonen we het betrouwbaar", niet
  "we herkennen elke AI-afbeelding".

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

## Combineren met PiHole

AuthentiPi en PiHole kunnen naast elkaar draaien, maar niet als twee losse
"primary/secondary" DNS-servers — een client gebruikt de tweede alleen als
de eerste niet reageert, dan werkt maar één van de twee functies
tegelijk. In plaats daarvan zet je ze serieel achter elkaar, met PiHole als
de server waar clients naar wijzen (onveranderd) en AuthentiPi als PiHole's
upstream:

```
Client → PiHole (blokkeert advertenties) → AuthentiPi (detecteert AI-domeinen) → 1.1.1.1 / 9.9.9.9
```

Instellen (aanname: PiHole en AuthentiPi draaien op aparte apparaten, dus
geen poort-53-conflict):

1. **In PiHole:** Settings → DNS → Upstream DNS Servers. Vink de
   standaardproviders (Google, Cloudflare, ...) **uit** en voeg bij
   "Custom 1 (IPv4)" het IP van je AuthentiPi-apparaat toe, bv.
   `192.168.1.50#53`. Laat je ook een standaardprovider aangevinkt staan,
   dan kan PiHole daarnaartoe in plaats van naar AuthentiPi — dan mis je
   detecties.
2. **In AuthentiPi:** niets aanpassen. `dns/dnsmasq.conf` blijft naar
   1.1.1.1/9.9.9.9 forwarden, dat blijft de laatste stap in de keten.
3. **Clients:** geen wijziging nodig, die wijzen al naar PiHole.

**Belangrijke kanttekening:** met deze volgorde ziet AuthentiPi altijd het
IP van de PiHole-server als "client" — niet het IP van het apparaat dat de
oorspronkelijke vraag stelde. DNS-forwarding geeft de oorspronkelijke
client niet door. Wil je per-apparaat detectie in AuthentiPi's dashboard
behouden, draai de volgorde dan om (`Client → AuthentiPi → PiHole`, met
AuthentiPi's IP als DNS-server in je router/DHCP-instellingen in plaats
van PiHole's IP) — dan ziet AuthentiPi het echte client-IP en blokkeert
PiHole nog steeds als AuthentiPi's upstream. Voor per-client detail bij de
"PiHole eerst"-opzet kun je PiHole's eigen Query Log (Tools → Query Log)
gebruiken en handmatig correleren op tijdstip.

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

## Content-marking testen (C2PA via de proxy)

De `proxy`-service (mitmproxy) onderschept HTTP(S)-verkeer van een client om
afbeeldingen te controleren op C2PA-manifesten en ze direct op de pagina te
markeren. Dit is ingrijpender dan de DNS-laag: al het verkeer van een client
die de proxy gebruikt, wordt ontsleuteld en geïnspecteerd.

### 1. CA-certificaat ophalen

mitmproxy genereert bij eerste start een eigen CA-certificaat in het
`mitmproxy-ca` volume. Haal het bestand op:

```bash
docker compose cp proxy:/home/mitmproxy/.mitmproxy/mitmproxy-ca-cert.pem ./mitmproxy-ca-cert.pem
```

### 2. Certificaat vertrouwen op het clientapparaat

- **iPhone:** stuur/AirDrop `mitmproxy-ca-cert.pem` naar het toestel, open
  het (installeert een geconfigureerd profiel), en zet 'm daarna **ook**
  aan onder Instellingen → Algemeen → Info → Certificaatvertrouwensinstel-
  lingen (dit is een aparte stap — anders wordt het certificaat wel
  geïnstalleerd maar niet vertrouwd voor TLS).
- **macOS:** dubbelklik het `.pem`-bestand om het aan je sleutelhanger toe
  te voegen, open het in Sleutelhangertoegang en zet "Altijd vertrouwen" aan.
- **Android:** Instellingen → Beveiliging → Meer beveiligingsinstellingen →
  Certificaten installeren → CA-certificaat.

### 3. Proxy instellen op het clientapparaat

Zet in de Wi-Fi-instellingen van het apparaat een HTTP-proxy (handmatig) op
het LAN-IP van AuthentiPi, poort **8081** (dezelfde plek waar je eerder de
DNS-server instelde).

### 4. Testen

De pagina moet je via **HTTP** bezoeken (niet als lokaal `file://`-bestand
openen) — alleen dan gaat de pagina zelf ook door de proxy, wat nodig is om
het marker-script erin te injecteren. Serveer het testbestand vanaf de
machine waar AuthentiPi op draait:

```bash
cd proxy/test-fixtures
python3 -m http.server 8090
```

Bezoek daarna vanaf het clientapparaat `http://<lan-ip-van-authentipi>:8090/content-marking-test.html`
(dezelfde LAN-IP als bij de DNS/proxy-instellingen). Die pagina embedt een
bekende C2PA-test-fixture uit de officiële `c2pa-python`-testset. Je zou een
klein "✓ Content Credentials"-badge in de hoek van de afbeelding moeten
zien, en een nieuwe rij op het dashboard onder "Content Credentials (C2PA)".

Wil je het met echte, zelf gegenereerde content proberen: gebruik een recent
met ChatGPT/DALL·E, Adobe Firefly of Google Gemini/Imagen gegenereerde
afbeelding, host die zelf, en verwijs er in een eigen HTML-bestand naar op
dezelfde manier.

**Let op:** de meeste bestaande afbeeldingen op het web hebben géén
C2PA-metadata — dit is nog een groeiende standaard. Test dus gericht met een
afbeelding waarvan je de herkomst kent, niet met een willekeurige site.

### Backend-contract los testen

`tests/test_content_marking.py` test de `/api/marks`-contractlaag (rapporteren
+ opvragen) rechtstreeks via de API, zonder dat de proxy of een echte
afbeelding nodig is — handig om snel te verifiëren dat backend en
`marker.js` het eens blijven over het formaat, ook als je aan de
proxy-addon (`proxy/authentipi_addon.py`) werkt.

### Beveiligingsafwegingen

- Er wordt volledig TLS-verkeer ontsleuteld van elk apparaat dat de proxy
  gebruikt — installeer het CA-certificaat dus alleen op apparaten die jij
  beheert en vertrouwt.
- De addon verwijdert `Content-Security-Policy`-headers van HTML-pagina's om
  het marker-script te kunnen injecteren. Dat verzwakt de beveiliging van
  bezochte sites voor het betreffende apparaat zolang de proxy actief is.
- Sommige sites met certificate pinning (bankieren-apps, sommige
  besloten apps) werken niet meer zolang de proxy actief is — dat is
  inherent aan MITM-interceptie, niet oplosbaar vanuit AuthentiPi.

## Domeinlijsten (`rules/`)

Zie [`rules/README.md`](rules/README.md) voor het formaat en hoe je eigen
lijsten toevoegt of abonneert op externe lijsten (net als PiHole-adlists).

## Licentie

MIT — zie [`LICENSE`](LICENSE).
