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

Vroege proof-of-concept. Fase 1, Fase 2 en Fase 3 hieronder zijn gebouwd en
getest.

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
- De badge toont, waar bepaalbaar, ook **wat voor soort content** het is
  (AI-gegenereerd, samengesteld, camera-opname, bewerkt — afgeleid van de
  `digitalSourceType` in de manifest-acties) en of de **ondertekenaar
  vertrouwd** is (geverifieerd tegen de officiële C2PA-trust-anchor-lijst,
  niet alleen "is er een manifest"). Manifesten die tamper-checks niet
  doorstaan worden genegeerd, niet gemarkeerd.
- Vereist het installeren van mitmproxy's CA-certificaat op clientapparaten
  (net als bedrijfs-firewalls doen) en het instellen van een HTTP-proxy op
  die apparaten. Zie "Content-marking testen" hieronder.
- **Belangrijke kanttekening over dekking:** C2PA is een nog groeiende
  standaard. Niet elke AI-afbeelding bevat een manifest (bijv. veel lokaal
  gedraaide Stable Diffusion-varianten doen dat niet), dus verwacht geen
  100%-dekking — dit is "als het er is, tonen we het betrouwbaar", niet
  "we herkennen elke AI-afbeelding".

**Fase 3 — experimentele lokale AI-beeldherkenning (opt-in, zwaar, onbetrouwbaar)**
- Voor content zonder C2PA-manifest (de meeste content op het web vandaag,
  inclusief veel echt AI-gegenereerd materiaal — zie hieronder) is er geen
  cryptografisch signaal om op te varen. `classifier`-service draait een
  lokaal ML-model (`umm-maybe/AI-image-detector` via `transformers`/`torch`,
  standaard instelbaar) dat een **statistische inschatting** maakt of een
  afbeelding AI-gegenereerd oogt.
- **Dit is nadrukkelijk geen verificatie.** Concreet gemeten op een
  afbeelding waarvan de eigenaar zeker wist dat 'ie AI-gegenereerd was:
  het model schatte "human" in met ~65-80% zekerheid — een valse
  negatieve op precies het soort geval waar dit voor bedoeld is. Op
  bekende echte foto's zat het model er wel goed naast (85-95% "human").
  Behandel de uitkomst als een hint, niet als een feit.
- Draait bewust niet standaard mee (torch/transformers zijn zwaar, ~1-2GB
  image, tragere cold start — merkbaar op een Raspberry Pi). Opt-in via
  een Docker Compose profiel én een losse toggle in de instellingen (zie
  hieronder), en visueel duidelijk anders gestyled dan de C2PA-badge
  (andere positie, eigen kleuren, toont het percentage) zodat een
  onzekere gok nooit hetzelfde oogt als een geverifieerde claim.

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
(dezelfde LAN-IP als bij de DNS/proxy-instellingen). Die pagina embedt zes
afbeeldingen die samen alle classificaties dekken die AuthentiPi
onderscheidt: AI-gegenereerd, deels AI-gegenereerd (samengesteld),
camera-opname, bewerkt, een generiek vertrouwd manifest, en een afbeelding
zonder manifest (negatieve test). Zie
[`proxy/test-fixtures/README.md`](proxy/test-fixtures/README.md) voor
details per variant. Je zou per variant een badge met de bijbehorende
classificatie moeten zien (of geen badge, voor de laatste), en nieuwe rijen
op het dashboard onder "Content Credentials (C2PA)" met Type- en
Vertrouwd-kolommen.

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
- De addon verwijdert conditionele cache-headers (`If-None-Match`,
  `If-Modified-Since`) van uitgaande requests en cache-headers van
  afbeeldingsresponses (`Cache-Control: no-store`). Zonder dit zou een al
  eerder bezochte afbeelding soms nooit meer over het echte netwerk gaan
  (browsercache of een lege 304-respons) — dan ziet AuthentiPi 'm ook nooit
  en blijft-ie voorgoed ongemarkeerd, ook al staat alles verder goed
  ingesteld. Kost iets meer bandbreedte/laadtijd (afbeeldingen worden niet
  meer lokaal gecachet zolang de proxy actief is), maar zonder deze stap
  faalt de kernfunctie stil voor precies het soort content dat je al eens
  bezocht hebt.

### Bekende beperkingen op drukke/dynamische sites

`marker.js` is getest tegen een eenvoudige statische testpagina, maar
zware, JS-gedreven sites (veel ads/trackers, responsive `srcset`-
afbeeldingen, infinite scroll) bleken in de praktijk vier extra dingen
nodig te hebben, inmiddels opgelost:

- **Mixed content (dé hoofdoorzaak van "geen badge op geen enkele echte
  site")**: `marker.js` werd eerst als absolute `http://<lan-ip>:8080/...`
  URL geladen. Op een HTTPS-pagina (vrijwel elke echte site) blokkeren
  browsers dat stil als "mixed content" — geen zichtbare foutmelding op de
  pagina, alleen in de devtools-console. Opgelost door de proxy-addon zelf
  als same-origin reverse-proxy te laten optreden: het script en alle
  API-calls lopen nu via een relatief pad (`/__authentipi/...`), dat de
  addon onderschept en intern doorstuurt naar de `app`-service — zo erven
  ze automatisch het schema (http/https) en de host van de bezochte pagina
  zelf, zonder dat AuthentiPi een eigen vertrouwd certificaat nodig heeft.
  Dit maakte ook de LAN-IP/`.env`-configuratie uit eerdere versies van dit
  document overbodig.
- **`srcset`/`<picture>`**: de browser kan een andere afbeeldings-URL laden
  dan wat in het `src`-attribuut staat. `marker.js` gebruikt nu
  `img.currentSrc` (de URL die de browser écht laadde) in plaats van alleen
  `src`.
- **CSP via een `<meta>`-tag**: sommige sites leveren hun
  Content-Security-Policy niet (alleen) als HTTP-header maar als
  `<meta http-equiv="Content-Security-Policy">` in de HTML zelf — dat
  wordt nu ook verwijderd, niet alleen de header.
- **Debounce-starvation**: bij continue DOM-mutaties (ads, trackers) kon de
  herscan-timer permanent gereset worden en dus nooit afgaan. Er draait nu
  ook een vaste interval-scan (elke 3s) als vangnet, die tegelijk fungeert
  als retry voor het geval een afbeelding nog niet klaar was met
  classificeren (Fase 3 kan een paar seconden duren) toen de eerste check
  liep.

## Experimentele AI-herkenning testen (Fase 3)

Werkt op dezelfde proxy-installatie als hierboven (CA-cert + proxy-instelling
moeten al staan). Extra stappen:

### 1. Classifier-service starten

Draait niet standaard mee met `docker compose up` — het is een zwaar,
expliciet opt-in profiel:

```bash
docker compose --profile experimental up -d classifier
```

Eerste keer bouwen duurt langer (torch + het model worden ingebakken in de
image, ~1-2GB). Check daarna `docker compose logs classifier` — moet
"Model geladen." tonen.

### 2. Aanzetten in de instellingen

Ga naar de instellingenpagina → "Experimentele AI-herkenning (Fase 3)" →
vink "Experimentele herkenning aanzetten" aan. De proxy roept de
classifier alleen aan voor afbeeldingen zónder C2PA-manifest, en rapporteert
alleen een detectie als de "artificial"-score de ingestelde drempel haalt
(standaard 0,6 — hoger = minder vals-positief, maar ook minder gevoelig).

### 3. Testen

Bezoek een pagina met een afbeelding waarvan je zeker weet dat 'ie
AI-gegenereerd is (en die geen C2PA-manifest heeft — anders vangt Fase 2
'm al af). Je zou onderin de afbeelding een oranje/amber badge moeten zien
met het percentage, duidelijk anders gestyled dan de gele C2PA-badge.

**Reken er niet op dat dit werkt.** Bij het testen tijdens de ontwikkeling
schatte het model een afbeelding waarvan de eigenaar zeker wist dat 'ie
AI-gegenereerd was, in als ~65-80% "human" — dus fout. Verlaag de drempel
in de instellingen als je specifiek dát soort grensgevallen wilt vangen,
maar besef dat dat ook meer vals-positieven op echte foto's oplevert. Dit
is precies waarom deze badge bewust anders oogt dan de C2PA-badge: het is
een gok, geen bewijs.

### 4. Drempel kalibreren met debug-modus

Zonder verdere info is de drempel bijstellen gokken: je ziet alleen iets
als een score 'm al haalt, dus je weet niet hoe dicht andere afbeeldingen
erbij zaten. Vink op de instellingenpagina **"Debug-modus"** aan (onder de
Fase 3-sectie) om dat zichtbaar te maken: dan rapporteert de proxy het
percentage van **elke** geclassificeerde afbeelding, ook ver onder de
drempel, als grijze/gestippelde badge met "debug: X% (onder drempel)".
Zo zie je de werkelijke spreiding van scores terwijl je de drempel
bijstelt, in plaats van alleen "wel/geen badge". Zet de debug-modus weer
uit als je klaar bent met kalibreren — hij is bewust bedoeld als tijdelijk
hulpmiddel, niet als permanente stand (elke afbeelding zonder manifest
krijgt er dan een zichtbare badge bij, ook de overduidelijk echte).

## TLS-uitzonderingen en foutlog

Onder **Instellingen → TLS-uitzonderingen** beheer je groepen zoals Apple
of Bankieren. De negen werkende hostnamen uit de App Store-proef worden
eenmalig als Apple geïmporteerd. Daarna is de database leidend;
`proxy/config.yaml` is alleen de initiële import en opstartfallback.

Groepen kun je toevoegen, hernoemen, uitschakelen en verwijderen. Voeg een
exacte hostnaam en poort toe, of verplaats een bestaande uitzondering door
dezelfde host/poort met een andere groep op te slaan. Een HTTPS-URL zonder
pad mag ook. Wildcards en URL-paden zijn niet toegestaan: het pad is vóór
TLS-ontsleuteling niet zichtbaar. Subdomeinen worden niet automatisch uitgezonderd.

De proxy haalt wijzigingen iedere drie seconden op, zonder herstart.
Heropen de betreffende app voor nieuwe verbindingen. Uitgesloten content
blijft versleuteld en wordt niet geïnspecteerd of gemarkeerd. Bij backenduitval
blijven de laatst geladen regels actief; die worden ook voor herstarts bewaard.

Het **TLS-foutlog** toont nieuwe mislukte handshakes met host, poort,
clientadres, foutzijde, laatste melding en aantal. Klik na een test op
**Log vernieuwen**, kies bij een fout een groep en klik op **Toevoegen aan
uitzonderingen**. Toevoegen gebeurt nooit automatisch. Een TLS-fout is
niet per definitie certificate pinning; een uitzondering lost niet elk
verbindingsprobleem op. Oude Docker-logs worden niet geïmporteerd.
De laatste 100 combinaties worden getoond, maximaal 500 worden bewaard.
Bij backenduitval of een volle rapportagebuffer kunnen meldingen verloren
gaan; proxyverkeer blijft doorgaan.

Geïsoleerde tests zonder wijzigingen aan de bestaande database:

```bash
docker compose exec -T app python - < tests/test_tls_settings_unit.py
```

## Domeinlijsten (`rules/`)

Zie [`rules/README.md`](rules/README.md) voor het formaat en hoe je eigen
lijsten toevoegt of abonneert op externe lijsten (net als PiHole-adlists).

## Todo

### Ideeën en gewenste richting

- [ ] **Configureerbare classifiers en een instelbare volgorde.** Maak het
  mogelijk classifiers toe te voegen, te selecteren en te configureren via
  een gedeelde interface, zodat meerdere mensen classifiers kunnen ontwikkelen
  die gespecialiseerd zijn in bepaalde taken. Laat geselecteerde classifiers
  achter elkaar draaien in een instelbare volgorde. Werk daarbij uit hoe
  resultaten worden doorgegeven en wanneer de volgende classifier draait
  of de keten stopt.
- [ ] **Dashboard verder uitwerken met statistieken.** Geef inzicht in
  onderzochte content, detecties per classifier en contenttype, trends in de
  tijd en verwerkingstijden. Houd C2PA-resultaten en statistische
  AI-inschattingen duidelijk van elkaar te onderscheiden.
- [ ] **Pi-hole-integratie zonder een tweede DNS-server.** Onderzoek en werk
  een opzet uit waarin Pi-hole de DNS-server blijft en AuthentiPi zonder eigen
  DNS-server kan draaien. De gewenste kernfunctie is content herkennen en
  markeren; alleen loggen dat een site bezocht is, is niet het doel. Bepaal
  welke onderdelen van de huidige DNS-laag daarmee kunnen vervallen of
  optioneel worden en documenteer hoe de proxy naast Pi-hole werkt.
- [ ] **Uitzonderingslijst voor URL's/domeinen.** Maak uitzonderingen
  configureerbaar zodat onder meer bankapps kunnen blijven werken met de
  proxy-opzet. Onderzoek een bypass voor TLS-inspectie bij certificate pinning
  en test dit op echte clients. Werk uit welke uitzonderingen op hostnaam
  moeten gelden voordat TLS wordt ontsleuteld en waar een volledig URL-pad
  bruikbaar is; alleen content-markering uitschakelen verhelpt een
  certificaatprobleem niet.

### Technische opvolging

Open punten op basis van de huidige projectstatus; onderstaande controles
zijn nog uit te voeren, ook waar de bijbehorende functionaliteit al gebouwd is.

- [ ] De recente wijzigingen aan de proxy en de opgesplitste
  instellingenpagina's controleren met de integratietests en een handmatige
  controle van het opslaan en terugladen van instellingen.
- [ ] Content-marking op echte HTTPS-sites en een apart clientapparaat
  opnieuw testen: same-origin script/API, `srcset`/`<picture>`, infinite
  scroll en badges bij vertraagde classificatie.
- [ ] Automatische regressietests toevoegen voor de proxy-injectie en het
  gedrag van `marker.js`; de bestaande API-contracttests dekken de volledige
  route van proxy naar zichtbare badge nog niet af.
- [ ] Een reproduceerbare set echte en AI-gegenereerde afbeeldingen zonder
  C2PA samenstellen om de classifier te evalueren; vals-positieven,
  vals-negatieven en het effect van de drempel vastleggen voordat een ander
  model of een andere standaarddrempel wordt gekozen.
- [ ] Geheugengebruik en classificatietijd op een Raspberry Pi meten, ook
  op pagina's met veel afbeeldingen; op basis daarvan bepalen of caching
  en begrenzing van classificatiewerk nodig zijn.
- [ ] Na de keuze voor de Pi-hole-integratie de installatiehandleiding voor
  een Raspberry Pi bijwerken. Als de eigen DNS-laag optioneel behouden blijft,
  ook de ontbrekende `dns/README.md` schrijven met poort 53 en
  router/DHCP-instellingen voor die opzet.
- [ ] De README bijwerken voor de opgesplitste instellingenpagina's en de
  uiteindelijke bediening van categorieën, lijsten, badges en AI-herkenning.

## Licentie

MIT — zie [`LICENSE`](LICENSE).
