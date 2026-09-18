# Domeinlijsten (rules)

AuthentiPi markeert netwerkverkeer op basis van domeinlijsten, vergelijkbaar
met hoe PiHole adlists gebruikt. Een lijst is een YAML-bestand met daarin
domeinen die bekend staan als (onderdeel van) een AI-contentdienst.

## Formaat

```yaml
# rules/default.yaml
name: "AuthentiPi default list"
entries:
  - domain: "chat.openai.com"
    service: "ChatGPT"
    category: "ai-text"
  - domain: "sora.chatgpt.com"
    service: "Sora"
    category: "ai-video"
  - domain: "midjourney.com"
    service: "Midjourney"
    category: "ai-image"
```

Velden:
- `domain` — de (sub)domeinnaam zoals die in DNS-queries voorkomt. Matching
  is exact op de queried hostname (geen wildcards in fase 1).
- `service` — leesbare naam van de dienst, gebruikt in het dashboard.
- `category` — één van `ai-text`, `ai-image`, `ai-video`, `ai-audio`,
  `ai-general`. Categorieën zijn aan/uit te zetten in de instellingenpagina.

## Eigen lijsten toevoegen

Zet extra `.yaml`-bestanden in deze map (of een gemount volume erbovenop) —
ze worden allemaal bij het opstarten geladen. Ondersteuning voor het
abonneren op een externe lijst-URL (zoals PiHole's adlist-subscriptions) staat
op de roadmap maar is nog niet geïmplementeerd.

## Waarom geen wildcard/domain-suffix matching in fase 1?

Om vals-positieven te beperken terwijl de lijst nog klein en handmatig
samengesteld is. Zodra de lijst groeit is subdomain-/suffix-matching een
logische volgende stap.
