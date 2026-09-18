# Overdracht van Codex aan Claude

Op verzoek van de gebruiker heeft Codex op 18 september 2026 een sectie
`Todo` aan `README.md` toegevoegd terwijl de Claude-sessielimiet bereikt was.
Dit verzoek is daarmee afgehandeld; voeg geen tweede todolijst toe.

De gebruiker heeft daarna de oorspronkelijke ideeën aangeleverd. Deze staan
nu onder `Todo` → `Ideeën en gewenste richting` in de README:

- Configureerbare, gespecialiseerde classifiers die door meerdere mensen
  ontwikkeld kunnen worden en in instelbare volgorde na elkaar draaien.
- Het dashboard uitbreiden met statistieken.
- Pi-hole-integratie onderzoeken waarbij AuthentiPi zonder eigen DNS-server
  draait; content herkennen en markeren is het doel, niet alleen sitebezoek loggen.
- Een uitzonderingslijst voor URL's/domeinen uitwerken, met een bypass voor
  TLS-inspectie om onder meer bankapps met certificate pinning te ondersteunen.

De eerder door Codex afgeleide punten staan onder `Technische opvolging`.
De DNS-documentatietaak is afhankelijk gemaakt van de keuze voor de
Pi-hole-integratie. De ideeën zijn alleen vastgelegd, nog niet geïmplementeerd.

Voor de todolijst zijn geen applicatietests uitgevoerd; de controles daarin
staan dus bewust nog open.

## Vormgeving dashboard en instellingen

Op aanvullend verzoek van de gebruiker heeft Codex de gedeelde stylesheet,
het basistemplate, het dashboard, de tabelpartials en de opgesplitste
instellingenpagina's vormgegeven. Licht/donker volgt automatisch de
systeemvoorkeur via `prefers-color-scheme`. De pagina's hebben kaarten,
actieve navigatie, mobiele layouts, scrollbare tabellen en toetsenbordfocus.
Het dashboard toont ook bestaande statistieken voor unieke clients en
categorieën; de backend en de formuliercontracten zijn hiervoor niet aangepast.
De overige ideeën blijven open.

De lokale app-container is opnieuw gebouwd en gestart. Browsercontrole met
Chrome/Playwright: alle vijf pagina's laden succesvol in licht en donker
op 1440 en 390 pixels breed, zonder horizontale pagina-overloop of
JavaScript-fouten. Het live C2PA-badgevoorbeeld is gecontroleerd, zonder
instellingen op te slaan. Screenshots van dashboard en badge-instellingen
zijn visueel nagekeken. `git diff --check` slaagt.

## App Store TLS-bypass (proef)

De gebruiker meldde dat de App Store op de iPad alleen zonder proxy werkt.
De proxylogs bevatten TLS-handshakefouten voor init.itunes.apple.com,
bag.itunes.apple.com en pd.itunes.apple.com. Deze drie exacte hosts op poort
443 staan nu in `proxy/config.yaml` onder `ignore_hosts`; Compose mount dit
als mitmproxy-configuratie. De proxy is opnieuw gestart. TLS-proeven via
poort 8081 tonen voor deze hosts het originele Apple-certificaat; example.com
krijgt nog het mitmproxy-certificaat. De bypass werkt dus technisch.
De gebruiker moet nog bevestigen of de App Store hiermee volledig werkt.
Andere iCloud-handshakefouten zijn gezien maar niet aan deze proef toegevoegd.
Er is nog geen beheerpagina voor uitzonderingen. Configwijzigingen toepassen
met `docker compose restart proxy`; een lege `ignore_hosts: []` schakelt de
bypass uit na herstart.

De eerste iPad-hertest mislukte nog. Nieuwe logs toonden twee TLS-fouten voor
`apps.mzstatic.com`. Deze exacte host op poort 443 is toegevoegd aan de
bypass en de proxy is herstart. De tweede iPad-hertest staat nog open.

Bij de tweede hertest werkten zoeken en detailpagina's nog niet goed.
Nieuwe TLS-fouten leidden tot exacte bypassregels voor is1-ssl.mzstatic.com,
amp-api-edge.apps.apple.com, amp-api-search-edge.apps.apple.com,
search.itunes.apple.com en gsa-gpk.apple.com. Proxy herstart; alle vijf
hosts geven via de proxy een geldig origineel certificaat door (geverifieerd
met systeemtrust en hostnaamcontrole). De gebruiker bevestigde vervolgens
dat de App Store hiermee goed lijkt te werken.

## Beheer TLS-uitzonderingen geïmplementeerd

Op verzoek is `/settings/tls` toegevoegd: groepen aanmaken/hernoemen/aan-uit/
verwijderen, exacte host-poortuitzonderingen toevoegen/verplaatsen/verwijderen,
en een TLS-foutlog met handmatige toevoeging aan een gekozen groep.
Nieuwe SQLite-tabellen worden via create_all aangemaakt. Een eenmalige
migratie importeert proxy/config.yaml als Apple; daarna is SQLite leidend.
tls_manager.py haalt elke 3s regels op, werkt ignore_hosts live bij, bewaart
de laatste configuratie in het CA-volume en rapporteert client/server
TLS-fouten via een begrensde asynchrone wachtrij. Opslag: maximaal 500
combinaties; UI: laatste 100. Oude Docker-logs worden niet geïmporteerd.
De marker reverse-proxy laat alleen benodigde read-only marker-endpoints
door, zodat sites via dat pad geen beheer-API kunnen benaderen.

Validatie: geïsoleerde backendtests plus Chrome/Playwright op mobiel/desktop
in licht/donker. Een echte TLS-fout voor example.com is vanuit het log aan
een tijdelijke groep toegevoegd: daarna origineel certificaat zonder
herstart; uitschakelen herstelde inspectie. Testgroep verwijderd.
Zie README voor gebruik en testopdracht. De eerdere handmatige
config.yaml/herstartinstructies zijn vervangen door beheer via de UI.
