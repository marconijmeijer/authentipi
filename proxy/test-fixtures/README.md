# Test-fixtures voor content-marking

`content-marking-test.html` embedt zes afbeeldingen die samen alle
classificaties dekken die AuthentiPi op dit moment onderscheidt:

| Bestand | C2PA-manifest | Type-classificatie | Ondertekenaar |
|---|---|---|---|
| `images/generic-credentials.jpg` | ja | geen actions-assertion | vertrouwd (echte Adobe test-signer) |
| `images/ai-generated.jpg` | ja | AI-gegenereerd | niet vertrouwd (self-signed) |
| `images/composite-ai.jpg` | ja | Deels AI-gegenereerd (samengesteld) | niet vertrouwd |
| `images/camera-capture.jpg` | ja | Camera-opname | niet vertrouwd |
| `images/edited.jpg` | ja | Licht bewerkt | niet vertrouwd |
| `images/no-manifest.jpg` | nee | n.v.t. | n.v.t. |

## Herkomst

- `generic-credentials.jpg` en `no-manifest.jpg` komen uit de officiële
  [c2pa-python](https://github.com/contentauth/c2pa-python) testset
  (`tests/fixtures/cloud.jpg` resp. `tests/fixtures/A.jpg`), Apache-2.0/MIT.
- De overige vier zijn lokaal gesigneerd met dezelfde SDK
  (`c2pa.Builder` + `c2pa.Signer.from_callback`) en het officiële
  ES256-testcertificaat uit diezelfde repo
  (`tests/fixtures/es256_certs.pem` / `es256_private.key` — een publiek
  bekend test-certificaat, geen echt geheim), elk met een eigen
  `c2pa.actions`-assertion en `digitalSourceType`
  (zie [IPTC digitalsourcetype vocabulaire](https://cv.iptc.org/newscodes/digitalsourcetype/)).

## Zelf uitbreiden

Wil je een extra variant toevoegen (bv. `algorithmicMedia` of
`compositeCapture`)? Download bovenstaande cert/key en een bronafbeelding
uit c2pa-python's `tests/fixtures/`, en gebruik hetzelfde patroon als
[`examples/sign.py`](https://github.com/contentauth/c2pa-python/blob/main/examples/sign.py)
uit die repo: een manifest met een `c2pa.actions`-assertion waarvan de
eerste actie `c2pa.created` is (verplicht, met een `digitalSourceType`),
gevolgd door eventuele vervolgacties. Zet het resultaat in `images/` en
voeg een `<div class="variant">`-blok toe in `content-marking-test.html`.
