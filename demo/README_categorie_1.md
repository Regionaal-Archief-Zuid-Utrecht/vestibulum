# Demo: toegangsbeperkingen e-depot (cat 1 + ALTCHA)

Minimale, self-contained demo van het consent-mechanisme voor
**categorie 1** (persoonlijke kopie na instemming) zoals beschreven in
`../requirements-toegangsbeperkingen.md` en
`../architectuur-toegangsbeperkingen.md`. Eén Python-bestand, alleen
stdlib — geen dependencies, geen database, geen echte S3.

## Starten

```powershell
# Docker (werkt overal, geen Python-installatie nodig)
docker run -d --name edepot-demo -p 8000:8000 `
  -v "<pad-na-deze-map>:/app" -w /app python:3.13-alpine `
  python categorie_1.py

# Of lokaal, als Python ≥ 3.10 aanwezig is:
python categorie_1.py
```

Daarna: **http://localhost:8000**

Handig:
- logs: `docker logs -f edepot-demo`
- stoppen: `docker stop edepot-demo` / weghalen: `docker rm -f edepot-demo`

## Wat de demo demonstreert

| Route | Rol |
| --- | --- |
| `GET /` | "Zoekresultaten" — documentlijst met categorie-badges |
| `GET /doc/<id>` | de "domme" viewer: HTML + piepklein JS dat aan de PEP vraagt wat te doen |
| `GET /resolve/<id>` | **de PEP** — enige plek die beslist |
| `GET /consent` / `POST /consent` | consent-endpoint: ALTCHA-proof-of-work + cookie uitgifte |
| `GET /file/<id>?exp&sig` | simuleert S3: alleen geldige presigned URL's |

## De flow

1. **Cat 0** (`krant-1953`) → `/resolve` geeft direct een "presigned"
   URL; `/file` serveert de bytes.
2. **Cat 1** (`tekening-001/002/003`, `tekening-010`, `losse-tekening`)
   → `/resolve` geeft `403 consent_required` **met instructie**:
   scope, terms-tekst, terms-versie, consent-URL én een
   proof-of-work-challenge. De viewer rendert dat letterlijk — hij
   bevat nul beleidslogica.
3. De pagina toont de voorwaarden + een ALTCHA-achtig widgetje: de
   browser lost `sha256(challenge+nonce)` met 3 leading zeros op
   (~1s CPU). Pas als dat lukt wordt "Ik stem in" actief.
4. `POST /consent` verifieert de PoW **server-side** en zet een signed
   cookie:

   ```json
   {"consented": ["dossier:dossier-bouw-1"],
    "terms_version": "2026-11", "pow": true, "exp": ...}
   ```

   gesigneerd met HMAC-SHA256 (`SECRET` in de code; in prod een
   JWT-bibliotheek + secret manager).

5. Volgende `/resolve`'s: cookie geldig én `terms_version` gelijk én
   de scope van het document in de cookie → presigned URL.

## De/demo-regels die je kunt uitproberen

- **Consent per dossier**: instemmen voor `dossier-bouw-1` dekt
  `tekening-001`, `-002` én `-003`, maar **niet** `tekening-010`
  (ander dossier) of `losse-tekening` (geen dossier → scope per
  document). Scopes cumuleren in de cookie.
- **Terms-versioning**: pas `version` in het `terms:default`-record
  (in `DOCS`) aan → alle bestaande cookies zijn direct ongeldig.
- **PoW is geen slagwerk**: `POST /consent` zonder/geldig-verkeerde
  `challenge`+`nonce` → `403 Proof-of-work mislukt`.
- **S3-simulatie**: open een `/file/...`-URL uit `/resolve`, knip de
  `sig` of `exp` → `403 AccessDenied`.
- **Cat 3** (`dossier-x`) → `login_required`; login/grants zijn in de
  demo bewust niet uitgewerkt.

## Bewuste vereenvoudigingen t.o.v. het echte ontwerp

- `DOCS` is een dict die de "index" simuleert; in prod komt
  `access_category`, `consent_scope` en de terms uit Elasticsearch
  (afgeleid uit RDF-sidecars bij indexatie).
- Geen rate-limiting, geen echte JWT (HMAC-token volstaat voor de demo),
  geen challenge-expiry of single-use challenges.
- Cookies zonder `Secure` (localhost is http); in prod verplicht.
- `/file` simuleert S3-presigned-validatie; er stromen geen echte bytes
  van S3.
