# Demo: afdwingen van toegangsbeperkingen (alle categorieën)

`afdwingen.py` — één Python-bestand (alleen stdlib) dat de
PEP-architectuur uit `../architectuur-toegangsbeperkingen.md`
simuleert: alle vier de categorieën, de twee PEP's, de
context-bewijzen en de scope-specifieke grants.

## Starten

Met Docker (map gemount, live reload bij herstart):

```
docker run -d --name edepot-demo-2 -p 8001:8000 \
  -v ".../architectuur/demo:/app" -w /app \
  python:3.13-alpine python afdwingen.py
```

of lokaal met Python ≥ 3.11: `python afdwingen.py` → http://localhost:8000

## Wat de demo laat zien

| Route | Rol in de architectuur |
| --- | --- |
| `/` | overzicht + huidige context (cookie/edge-claims) |
| `/doc/<id>` | domme viewer — rendert wat de PEP teruggeeft |
| `/resolve/<id>` | **PEP voor bytes**: beslist, geeft URL of 403+instructie |
| `/search?q=` | **ES-proxy**: afgeschermde snippets zonder context; hits nooit gedropt |
| `/consent` | instemming cat 1: dossier-scoped, ALTCHA PoW, terms_version |
| `/login` | OIDC-simulatie: claim van eigen IdP → `granted:org:<naam>` |
| `/grant` | beheer-simulatie: verleent `granted`-scope (doc:/dossier:) |
| `/edge/...` | simuleert de **edge**: alleen deze route stempelt studiezaal-IP |
| `/file/<id>` | S3-simulatie: alleen geldige presigned URL's |

## Te proberen

1. **Consent is geen gratis pas**: stem in op `tekening-001` →
   `tekening-002` werkt meteen (zelfde dossier), maar `vergunning-001`
   (cat 2, *zelfde* dossier) blijft studiezaal-vereist.
2. **Grant dekt de hele scope**: verleen via `/grant` toegang op
   `dossier:dossier-bouw-1` → `vergunning-001` opent nu wél — de toegang
   loopt "via categorie 3", de basiscategorie doet er niet toe.
3. **Studiezaal = bewijs, geen claim**: `krant-1943` geeft in normale
   weergave een instructie; via de `/edge/`-weergave (gesimuleerde
   studiezaal-terminal) krijg je een presigned URL.
4. **Org-toegang**: log in als "gemeente Houten" → documenten van die
   archiefvormer openen, ook cat 3 en cat 2; andere organisaties niet.
5. **ES-proxy**: zoek op "tekening" zonder context → hits blijven,
   snippets zijn afgeschermd. Met consent/grant zijn ze leesbaar.
6. **Manipulatie**: pas de `sig` in een `/file`-URL aan → 403.

## Bewuste vereenvoudigingen

- "ES-index" = een dict; "S3" = fake bytes; signing = HMAC.
- De edge is een URL-prefix (`/edge/`); in productie zet de
  infrastructuur het studiezaal-IP.
- Login/grant zetten een signed cookie in dezelfde browser; in
  productie komt de claim van een echte IdP (OIDC) of het
  beheersysteem.
- Geen rate-limiting, geen challenge-expiry, geen echte ALTCHA.
