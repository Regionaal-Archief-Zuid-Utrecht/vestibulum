











....

Het e-depot bevat materiaal met verschillende toegangsniveaus; de huidige
opzet ondersteunt alleen volledig publiek (of niet toegankelijk). 
Doel: de geldende beperkingen afdwingen — degelijk, veilig, efficiënt, beheerbaar.

Berpelk



## 2. Toegangsmodel

Categorieën 0–4 zijn het **beleidsvocabulaire**.
Operationeel zijn het twee vragen — **vindbaarheid** (mag de inhoud meedoen
in full-text zoeken; afdwinging is structureel via wel/niet indexeren van
`full_text`) en **content** (mag de inhoud getoond/geleverd worden: snippets
én bytes volgen dezelfde regel, één veld) — zodat afdwijnpunten (*policy
enforcement points*, PEP's) de categorie niet zelf interpreteren:

| Cat | Omschrijving                                                       | `full_text` geïndexeerd | `content_access` |
| --- | ------------------------------------------------------------------ | ------------------- | ---------------- |
| 0   | Geen beperkingen                                                   | ja                      | `public`         |
| 1   | Beperkt: online na instemming (privégebruik)                       | ja                      | `consented`      |
| 2   | Niet publiek: alleen RAZU-studiezaal                               | ja                      | `studyroom`      |
| 3   | Openbaarheidsbeperking — op aanvraag; volledig vindbaar via metadata én content (m.n. fulltext) | ja  | `granted` |
| 4   | Openbaarheidsbeperking — op aanvraag; beperkte doorzoekbaarheid van content én metadata | **nee** | `granted` |

Cat 3 is volledig vindbaar — metadata én fulltext — maar snippet én
bestand vragen een grant. Cat 4 heeft beperkte doorzoekbaarheid: geen
`full_text` (dus geen highlight) én restricted metadata-velden blijven
buiten publieke zichtbaarheid (4.6); zo'n document komt alleen via
reguliere metadata-matches in beeld.

De tabel heeft bewust twee assen. Een tweede beleidsbeslissing geldt
per veld: **veldbeperkingen** (4.6) — welke velden niet worden
meegeïndexeerd. Die gelden los van de categorie — ook een
cat-0-document kan een restricted persoonsnaam bevatten — en worden
net zo structureel afgedwongen als `full_text` bij cat 4: wat niet
geïndexeerd is, is onvindbaar en ontoonbaar, punt.

De RAZU-kranten zijn een voorbeelbeeld van categorie 0. Uitzonderingen hierop zijn de kranten met auteurechtelijke beperkingen. Die zijn categorie 2: er worden online geen snippets getoond behalve in de studiezaal In de studiezaak is de krant ook te bekijken. Een voorbeeld van categorie 1 zijn de tekeningen van bouwvergunningen. Daar kunnen auteurrechtelijke beperkingen op zitten. We vragen gebruikers daarom om eerst er mee in stemmen het materiaal niet met anderen te delen. Na die instemmingen krijge ze toestemming. 

- Snippet ís content: `content_access` geldt voor het tonen van fragments
  én voor het ophalen van bytes.
- "Een hit bewijst dat een term voorkomt in een beperkt bestand" is
  geaccepteerd — geen categorie-filter op de query.
- Prioriteit: cat 3 laag; cat 4 gebruikt hetzelfde `granted`-mechanisme.

Sectorcontext: het KVAN-kennisdocument *Beschikbaar stellen
Bouwdossiers* (dec. 2023) beschrijft vrijwel dezezelfde maatregelen als
gangbare sectorpraktijk (studiezaal, disclaimer-consent, aanvraag-links,
niet op persoonsnaam doorzoekbaar, org-toegang voor ambtenaren) — dit
ontwerp maakt die maatregelen centraal en consistent afdwingbaar.

## 3. Principes

1. **Afdwijnpunten (PEP's), geen client.** De viewer communiceert categorie,
   dwingt nooit af. PEP's: ES-proxy (zoeken/snippets) en resolver (bytes).
2. **RDF is de bron; categorieën worden één keer afgeleid, bij indexatie.**
   ES is hét leesmodel voor alle subsystemen (zoeken, resolven, drift);
   RDF is het schrijfmodel en wordt niet runtime bevraagd.
3. **URI ≠ delivery-URL.** De canonieke URI is een schone identifier;
   voor cat ≥ 1 is fetchen daarvan terecht `403`. Bytes gaan via een
   vluchtige presigned URL die S3 zelf valideert — geen byte-proxy,
   geen token in de canonieke URI.
4. **Context uit bewijs, niet uit claims.** Signed cookie + client-IP;
   nooit headers/parameters die de client zelf stuurt.
5. **Geen byte-proxy's.** PEP's signeren of weigeren; bytes komen
   direct van S3/CDN/LAN.

## 4. Componenten

### 4.1 Indexer

- **Afleiding**: `beperkingGebruik` (type + termijn, meerdere per record)
  → categorie via een versiebeheerde **mappingtabel** (beleid, geen code).
  Meerdere beperkingen: de strengste wint, ook met verschillende termijnen
  (lopende cat-2 naast verlopende cat-1 → cat 2 tot einddatum; testcase).
  Verstreken termijnen tellen niet mee. De input (types + einddatums)
  wordt meegeïndexeerd — nodig voor her-afleiding en drift-detectie.
- **Twee velden per document**: `access_category` (badge/rapportage) en
  `content_access` (proxy én resolver — tonen van een fragment volgt
  dezelfde regel als levering van de bytes). Vindbaarheid heeft geen veld
  nodig: die volgt uit het wel/niet indexeren van `full_text`.
- **Erf over de hiërarchie**: beperkingen zitten op beschrijvingsniveau
  (issue, archiefstuk); de effectieve categorie van een document volgt
  uit zichzelf + alle voorouders, strengste wint.
- **`files`-index**: aparte, niet-search-facing index; per bestand
  `{uri, content_access, access_org, parent_id, s3_bucket, s3_key,
  media_type}`.
- **`access_org`**: welke organisatie "eigenaar" is van het stuk —
  de archiefvormer-URI van de (dichtstbijzijnde) beschrijving, meegekopieerd
  op zoekdocument én `files`-rij. Nodig voor org-scoped grants (4.4):
  de PEP vergelijkt per hit `granted:org:<uri>` met dit veld.
  Resolver leest categorie én coördinaten direct af — geen
  URI→key-heuristiek, geen lek in zoekresultaten/aggregaties. Bestanden
  erven de oudercategorie — de ALTO (bevat OCR) is daarmee bij cat 4
  even beschermd als de ontbrekende `full_text`.
- **Indexatie**: cat 0–3 → metadata + `full_text`. Cat 4 → alleen
  metadata — afdwinging is structureel, geen runtime-filter.
- **Verversing** — drie triggers:
  - *termijnverloop* (verlaging): dagelijkse her-afleidingsjob volstaat;
  - *aanscherping* (striktere beperking/ingekorte termijn): direct —
    geen dag te ruime levering;
  - *mappingwijziging*: deploy triggert her-afleidingsjob.
- **Transitie**: eerst de lichte afgeleide velden bulk-updaten op alle
  geraakte docs + `files`-index (minuten; PEP's handhaven direct
  de nieuwe toestand — de velden zíjn de pending-flag), daarna async het
  zware werk (`full_text` verwijderen/herindexeren bij 3↔4, S3-sync).
  Beheer meldt "actief" na de velden-update; audit logt beide tijdstippen.
  Een aparte pending-registratie is een optie mocht ook dat venster
  onacceptabel zijn — nu niet gekozen (hot path blijft één-bron).
- **Consolidatie**: de viewer leidt nu zelf beperkingen af (SPARQL per
  record); in de doelsituatie leest hij alleen `access_category`.
- **Fan-out**: transitie op issue/archiefniveau raakt honderden tot
  tienduizenden docs × bestanden → asynchroon, gebatched, met voortgang
  in beheer.

### 4.2 ES-proxy

Enige ingang tot Elasticsearch (netwerk-afgedwongen). Drie taken:

1. **Context bepalen** uit signed cookie + client-IP (studiezaal via
   allowlist, nooit client-headers).
2. **Query doorsturen** — ongewijzigd; restricted velden staan niet
   in de index (4.6), dus er is ook niets te filteren in queries,
   `_source` of aggregaties.
3. **Response-hygiëne** per hit: `content_access` vereist een context die
   ontbreekt → `hit.highlight` strippen of door marker vervangen. Hits
   worden **nooit gedropt** — ook niet tijdens een 3→4-transitie, waarin
   een document tot de herindexering nog op `full_text` kan matchen; dat
   is term-presence zonder fragment, hetzelfde geaccepteerde residue als
   bij cat ≤ 3. `Cache-Control: private`.

**Voorbeeld.** `content_access` zit in `_source` en komt met elke hit
gratis mee; de query hoeft dus hooguit uitgebreid met een
`_source.includes`. Een cat-2-hit onder publieke context:

```json
{ "_source": { "title": "Utrechts Nieuwsblad, 2 feb 1953",
               "access_category": 2, "content_access": "studyroom",
               "URL_bestand": ["https://cdn…/p002.alto.xml"] },
  "highlight": { "full_text": ["…na de <em>watersnood</em> werd…"] } }
```

wordt door de proxy tot:

```python
if not allowed(context, hit["_source"]["content_access"]):
    hit.pop("highlight", None)        # hit blijft, fragment weg
```

`allowed()` vergelijkt op de rangorde `public < consented < studyroom`,
plus `granted:{ids}` voor de genoemde IDs. Ontbreekt `content_access` op
een hit → fail-closed defaulten op meest restrictief. `hits.total`,
sortering en paginering blijven onaangeraakt.

### 4.3 Viewer

- Badge per resultaat op `access_category`; consent-flow linkt naar het
  consent-endpoint.
- Restricted detailpagina's krijgen `noindex` — externe zoekmachines
  indexeren alleen publiek materiaal; presigned URL's zijn vanzelf
  onindexeerbaar.
- Één URL-resolutie-haak: metadata bepaalt of een URI direct fetchbaar is
  of via de resolver loopt.
- Studiezaal = zelfde build, lokaal gedeployed; herkenning via IP, de
  viewer claimt niets.

### 4.4 SURA — entitlement-issuer + resolver

Doorontwikkeling van "URL → JWT"; bouwstenen bestaan (`generate_presigned_url`
incl. Scality-endpoint, `/_search`-forward, IP-detectie). De delta zit in
de beslislaag: lookup → context → teruggeven/presignen/weigeren.

- De `private`-modus (byte-proxy) vervalt; de `public`-JWT-machinerie
  kan dienen als cookie-uitgever (andere claims, zelfde tekentechniek).
- `forwarded_ip`-queryparam verdwijnt als autorisatie-signaal (spoofbaar).
- **Cookie**: één signed JWT, `{scopes:[...]}` — vóór fase 2 vastleggen
  (later wijzigen is breaking). `HttpOnly`, `Secure`, `SameSite=Lax`,
  alleen naar de resolver (géén CDN-domein; pas bij Vorm B gedeeld).

| Scope           | Herkend via                          | Geeft        |
| --------------- | ------------------------------------ | ------------ |
| `public`        | default                              | cat 0        |
| `consented`     | cookie-claim (na "ik stem in")       | cat ≤ 1      |
| `studyroom`     | client-IP in allowlist — géén claim  | cat ≤ 2      |
| `granted:{ids}` | cookie-claim (beheer), met expiry    | cat 0 + ids  |
| `granted:org:{uri}` | cookie-claim (federated login)   | alles van die archiefvormer |
| `granted:*`     | cookie-claim (federated login, uitz.) | alle content |

- **Scopes stapelen**: IP-signaal + claims vormen samen de context; elke
  check pakt de ruimste. Studiezaal zit bewust níet in het cookie.
- **`granted:org:{uri}`** is de gedelegeerde route: een medewerker van
  gemeente X die inlogt krijgt toegang tot álle beperkte content met
  `access_org == X` (eigen archief is volledig bereikbaar, ongeacht
  categorie). `granted:*` is voor partijen zoals brandweer die alles
  moeten kunnen inzien. Beide raken alleen **content-levering** — de
  cat-4-regel (geen `full_text` in de index) is structureel en wordt
  door geen enkele grant doorbroken.
- **`allowed()`-uitbreiding**: naast de rangorde en `{ids}` geldt een hit
  als toegestaan bij `granted:*` óf `granted:org:<hit.access_org>`.

### 4.4.1 Federatieve login (delegatie aan bronorganisaties)

Vraag: specifieke gebruikers (bv. brandweer) krijgen toegang tot alles,
en gemeente-medewerkers tot alles van de eigen gemeente — zónder dat
RAZU gebruikersadministratie voert.

- **Identiteit komt van de eigen organisatie, via de open standaard
  OIDC.** Elke OIDC-compliant IdP kan aangehaakt — gemeenten draaien
  doorgaans Entra ID, maar Keycloak, SURFconext of een eigen
  open-source provider werkt identiek; de resolver ziet het verschil
  niet. Een eenmalige OIDC-koppeling per organisatie volstaat. Wie in
  welke groep zit, beheert de organisatie zelf — dat ís de delegatie.
  RAZU voert géén user-database.
- **Mapping is beleid, geen administratie**: een kleine versiebeheerde
  tabel `IdP-claim → scope` (bv. `tenant:gemeente-x.nl → granted:org:<uri>`,
  `group:veiligheidsregio → granted:*`), net als de categorie-mapping.
- **Login-flow**: `GET /login` → OIDC bij gekozen IdP → SURA mint het
  bestaande signed cookie met de afgeleide `granted:`-claims. De PEP's
  zien dus nul verschil met handmatig uitgegeven `granted:{ids}` —
  zelfde cookie, zelfde check.
- **Leverancier-onafhankelijk**: OIDC is het enige contract (discovery
  + claims); de organisatie kiest zelf haar IdP. SAML kan technisch
  ook maar voegt alleen complexiteit toe — niet gekozen. eHerkenning
  is disproportioneel (kosten, brokers); SURFconext kan als
  OIDC-broker dienen voor organisaties zonder eigen koppelbare IdP.
- **Wachttijd/levering**: na login werkt alles op claims; geen extra
  round-trips per resolutie.
- **Consent** is sessiebreed (één "ik stem in" dekt alles; ~24u) en
  bewust symbolisch — crawler- en per-ongeluk-wering, geen autorisatie;
  het cookie-format staat er om `granted`, niet om consent. Sectorbreed
  bestaat ook een identificeerbare variant van dezelfde scope
  (e-mail + disclaimer → link naar dossier); dat is dezelfde
  `consented`-mechaniek, geen aparte categorie.
- **Fail-closed**: resolver-uitval → geen cat ≥ 1-levering; cat 0 (CDN)
  blijft werken.
- **Audit bij cat ≥ 2**: scope/grant-ID, IP, URI, tijdstip — wettelijke
  verantwoording én incident-onderzoek. Cat 1 niet log-waardig.
- **Grant dekt de hiërarchie**: grant op issue dekt pagina's + bestanden
  (consistent met erf-regels).
- **Resolver-flow**: `GET /resolve/<uri>` → `files`-index-lookup →
  context-check → presigned S3-URL (TTL ~min) in body of als `302`.
  Bytes lopen nooit door SURA. Batch-variant (lijst URI's) is een
  nuttige uitbreiding voor IIIF-clients.
- **Eén S3-servicecredential** (`s3:GetObject`) volstaat; differentiatie
  zit vóór het signen.

### 4.5 Opslag en CDN

CDN kan per distributie alleen "JWT verplicht" aan/uit — geen regels of
edge-logica. Twee vormen:

- **Vorm A (aanbevolen)**: CDN publiek-only — cat ≥ 1-objecten zijn
  non-public (`403`, bevestigd) en gaan via presigned S3. Nul CDN-config;
  geen edge-caching van beperkt materiaal (gewenst).
- **Vorm B (later, als caching wenselijk)**: tweede distributie, JWT
  verplicht voor alles, resolver als enige uitgever.

Cat-2-bytes mogen in de studiezaal vanaf LAN komen (bonus). IIIF-image-
server: als die server-side uit S3 leest, geldt de check óók voor tiles —
verifiëren bij implementatie. 3-2-1 blijft: S3 (non-public) + LAN + offline.

### 4.6 Veldbeperkingen (veldniveau)

Restricted velden (bv. persoonsnamen onder AVG) worden bij indexatie
simpelweg **niet meegenomen** — structurele afdwinging zoals bij
cat-4-`full_text`: er staat niets in de index om te lekken, dus de
proxy heeft geen veldtaak (geen strip uit `_source`, geen filter op
queries of aggregaties).

Gevolg: die velden zijn via de portal voor niemand doorzoekbaar of
toonbaar — ook niet voor medewerkers met `granted:org`. Legitieme
naam-zoekopdrachten voor medewerkers lopen via het beheersysteem (de
bron van waarheid), niet via de publieke zoekvoorziening. Is zoeken op
restricted velden voor geautoriseerde contexten in de portal alsnog
gewenst, dan is een context-gated veld (voorheen `restricted_terms`,
strip via `allowed()`) de escape hatch — zie open punten.

**RDF-zijde**: metadata leeft ook in de triplestore. Daar geldt
dezelfde beperking op datasetniveau — de metadata splitst in een
**openbare dataset** (de publieke SPARQL-endpoint, waar de viewer en
externe clients op bevragen) en een **besloten dataset** met de
restricted velden. Het endpoint filtert niets: wie de besloten
dataset mag bevragen heeft volledige toegang, wie niet heeft er
geen — de afdwinging zit in de datasetsplitsing zelf, niet in
query-regels. Hoe toegang tot de besloten dataset wordt verleend
(medewerkers-authenticatie) wordt hier niet uitgewerkt. De indexer
leest de volledige interne metadata; welke velden restricted zijn,
volgt uit dezelfde mapping als de ES-veldbeperking.

### 4.7 Beheerinterface

- Beperkingen bewerken via de `beperkingGebruik`-structuur in RDF
  (type, termijn, einddatum), nooit direct een categorie zetten.
- Volgeffecten automatisch: her-afleiding → velden-update (direct bij
  aanscherping) → structureel werk + `files`-index + S3-beleid async.
- Grant pas uitgeven ná voltooiing van de velden-update op de gedekte
  docs — versheid uit schrijfvolgorde, geen tweede leespad.
- Geeft `granted:{ids}` uit (scoped, met expiry) — voor ad-hoc
  individuele grants.
- Org-scoped toegang valt **buiten** deze interface: de organisatie
  kent die toe in haar eigen IdP (groepslidmaatschap); RAZU beheert
  alleen de trust-config en de claim→scope-mapping (4.4.1).
- Drift-overzicht per record: RDF-structuur naast ES-velden,
  `files`-index-rij en S3/CDN-beleid.

### 4.8 Snippetservice (vervalt)

De proxy neemt de chokepoint-rol goedkoper over (ES-highlights i.p.v.
ALTO re-parsen). Te behouden: welke pagina een match bevat — vereist een
positieveld op page-documenten.

## 5. Niet-functioneel

- **Veiligheid**: ES nooit direct publiek; signed kortdurende entitlements;
  studiezaal alleen IP-gebaseerd.
- **Efficiëntie**: geen byte-proxy's; snippets uit ES-highlights; resolver
  is lichte 302-hop; CDN-cache voor cat 0.
- **Beheerbaarheid**: één bron (RDF), één uitgever (SURA), één PEP
  per asset-type.
- **Open standaarden**: OIDC voor federatieve identiteit, JWT voor
  entitlements, presigned S3 voor delivery — geen lock-in, elke laag
  is vervangbaar.
- **Privacy**: AVG-termen niet indexeren (veldbeperking).

## 6. Afwegingen en valkuilen

- **Denormalisatie-belasting (bewuste keuze)**: de velden zijn een kopie
  van wat RDF voorschrijft → fan-out, verversingsjobs en drift-detectie
  zijn de prijs. Alternatief (resolver/proxy leidt live af + cache) is
  verworpen: runtime-hiërarchie-walks per request en per hit, plus een
  tweede interpretatieplek. Per-hit gating vereist velden óp de hit.
- **Aggregaties**: restricted velden staan niet in de index, dus
  facets kunnen ze niet lekken; wat blijft is term-/facet-presence op
  reguliere metadata van beperkte docs — dat is hetzelfde geaccepteerde
  residue als de zoek-hit zelf.
- **"Mysterieuze" hits**: cat-2-doc dat alleen op OCR matcht toont een
  badge, geen snippet — bewuste UX.
- **Header-spoofing**: alleen edge-gezet client-IP voor studiezaal;
  `forwarded_ip` is geen autorisatie-signaal.
- **Cache-lekkage**: context-afhankelijke antwoorden altijd `private`.
- **Dev/prod-pariteit**: demo-ES staat op `localhost:9200`; in productie
  is de proxy de enige route.
- **Drift** = beheerincident: vergelijkt RDF ↔ ES-velden ↔ `files`-index
  ↔ S3-beleid; veroorzaakt door termijnverloop, mappingwijziging of
  mislukte transitie → vandaar de her-afleidingsjobs en drift-weergave.
- **Afleiding op één plek**: client-side interpretatie van beperkingen
  vervalt; `access_category` is leidend.

## 7. Fasering

0. **Nu — vooronderzoek**: Scality-checks a–d (§8); SURA-prototype in
   drie stappen ((1) `/process-url` + categorie-stub + beslismatrix +
   presigned-return, (2) echte `files`-lookup, (3) cookie-context →
   cat 1 end-to-end; viewer-interface blijft identiek). Mappingtabel als
   parallelle **beleidstrack** — geen code, wel voorwaarde voor fase 1.
1. Afgeleide velden in index + ES-proxy met context + response-gating
   (snippetservice vervalt; cat-4-regel geldt direct).
2. Resolver + Vorm A + consent-flow → cat 1 publiek.
3. Studiezaal-instantie + IP-context → cat 2.
4. `granted:{ids}` + beheer-uitgifte + veldbeperkingen → cat 3 en 4.
5. Beheerinterface: editing, transitie-triggers, drift-weergave.
6. Federatieve org-toegang: `access_org` mee-indexeren, OIDC-login per
   organisatie, claim→scope-mapping → `granted:org:{uri}` en
   `granted:*` (brandweer-achtige partijen). Kan eerder als één
   organisatie aanhaakt; de PEP-check is generiek.

## 8. Open punten

- **Scality-checks** (blokkeren fase 1): (a) service-account met
  `s3:GetObject`; (b) path- vs virtual-hosted addressing; (c) **CORS op
  het S3-endpoint** — `<img>` overleeft zonder, XHR/`fetch` (IIIF, ALTO)
  niet; (d) Vorm B: CDN geeft signed querystrings/cookies door.
- **IIIF-image-server**: bepaalt deze het byte-pad? Dan geldt de check
  ook voor tiles.
- **Veldbeperkingen**: volstaat niet-indexeren (aanname)? Twee
  randgevallen: (a) restricted term ín een publiek document —
  bijvoorbeeld één naam in een verder openbaar stuk; (b) is zoeken op
  restricted velden voor geautoriseerde contexten in de portal ooit
  nodig — dan is een context-gated veld (strip via `allowed()`, zoals
  highlights) de escape hatch.
- **TTL's**: cookie ~sessie/24u, delivery-URL ~minuten (voorstel).
- **SURA als generieke entitlement-issuer** vs. apart identity-component.
- **Mappingtabel** formaliseren: verzamel alle `beperkingGebruikType`-
  termen, beslis per term (beleidstrack parallel aan fase 0/1).
- **Studiezaal-NAT**: welk publiek IP/subnet presenteren de clients —
  blokkeert anders cat-2 in fase 3.
- **`access_org`-bron**: welk RDF-veld bepaalt "van welke organisatie is
  dit stuk" — `archiefvormer` (erfbare beschrijvingswaarde) of een
  beheerder/eigenaar-predicaat? Bevestigen op productiedata; de
  demo-index bindt RAZU zelf als archiefvormer.
- **IdP-inventarisatie**: welke IdP kan elke aangesloten gemeente
  koppelen (Entra-tenant, OIDC-discovery, groepsclaims)? Bepaalt of
  één variant volstaat of er een fallback-accountroute nodig is.
- **Claim→scope-mapping**: formaat vastleggen (welke claims vertrouwd
  worden: tenant, groep, domein) en hoe uitzonderingen als
  `granted:*` worden afgegeven en gexpireerd.
- **Org-scope en cat 2**: nu dekt `granted:org` álle categorieën van
  de eigen archiefvormer (eigen archief volledig bereikbaar) —
  bevestigen dat studiezaal-materiaal inderdaad online aan eigen
  medewerkers getoond mag worden.
- **Conditionele termijnen**: sommige beperkingen lopen af op een
  gebeurtenis ("zolang het gebouw die functie heeft", "zolang betrokkene
  leeft") in plaats van een datum — de her-afleidingsjob kan die
  condities niet zelf evalueren; beheerinterface meldt af, of er komt
  een externe triggerbron.
- **Register Overledenen**: het overlijdensregister (1939–heden) als
  automatische haak om privacy-beperkingen te laten verlopen —
  overleden betrokkene → beperking vervalt.
- **Granulariteit per document-type**: binnen één dossier kunnen
  stukken verschillende regimes hebben (aanvraagformulier met BSN vs.
  tekening) — de erfregels dekken dit, maar RDF-modellering van
  beperking-op-stuktype plus een testcase verdienen aandacht.
- **Regime-grens WOO/Archiefwet**: het model veronderstelt
  overgebracht materiaal (Archiefwet, "beperkt openbaar" bestaat).
  Niet-overgebrachte dossiers vallen onder de WOO, waar openbaar
  binair is — org-toegang voor eigen medewerkers is daar intern
  gebruik, geen openbaarmaking; vastleggen hoe dat in de metadata
  herkenbaar is (overbrengingsstatus).



/////


# Architectuur voorziening afdwingen toegangsbeperkingen RAZU e-depot

## Probleemstelling

## Model en principes

Gehanteerd principe is dat bezoekers online ten minste het bestaan van
alle dossiers moeten kunnen ontdekken. Ze hebben echter niet altijd
toegang tot alles. We maken hierbij onderscheid tussen 5 categorieen:

0. **Publiek beschikbaar** materiaal, online te vinden en te bekijken.
1. **Beperkt publiek beschikbaar** materiaal. Na instemming met specifieke
   condities krijgt de gebruiker tijdelijk toegang.
2. **Niet-publiek beschikbaar** materiaal. De gebruiker moet hiervoor naar
   de studiezaal.
3. **Openbaarheidsbeperking** — beperkt openbaar materiaal. Volledig
   vindbaar via metadata én fulltext; gebruikers moeten toestemming
   vragen aan de directeur-archivaris, alvorens mogelijk toegang te
   krijgen.
4. **Openbaarheidsbeperking met beperkte doorzoekbaarheid** — ook de
   vindbaarheid van content én metadata is ingeperkt: de fulltext komt
   niet in de index en gevoelige metadata-velden zijn niet publiek
   doorzoekbaar, om te voorkomen dat via zoekopdrachten te veel van de
   inhoud achterhaald kan worden.

De RAZU-kranten zijn een voorbeeld van categorie 0. Uitzonderingen hierop
zijn de kranten met auteursrechtelijke beperkingen: die zijn categorie 2 —
de krant is niet online te bekijken en er worden online geen tekstsnippets
vertoond; in de studiezaal is de krant wél te bekijken. Een voorbeeld van
categorie 1 zijn de tekeningen van bouwvergunningen: daar kunnen
auteursrechtelijke beperkingen op zitten. We vragen gebruikers daarom eerst
in te stemmen met de voorwaarde het materiaal niet met anderen te delen;
na die instemming krijgen ze automatisch toestemming.

## De componenten hoogover

De viewer of zoekvoorziening dwingt zelf geen regels af; dat gebeurt er
vóór. Voor het opvragen van bestanden is een resolver het afdwingpunt —
in vaktermen de *policy enforcement point* (PEP). Ook de
Elasticsearch-proxy is een PEP, want daar wordt bepaald of
tekstfragmenten (snippets) van de fulltext doorgegeven mogen worden. De
policy voor snippets is identiek aan de policy voor de content zelf.

De *policy decision point* (PDP) — de plek waar vastgelegd wordt welke
regels voor ieder document gelden — is in het RAZU-model de
indexeersoftware. Tijdens het indexeren wordt (a) de categorie bepaald
die voor het document geldt, en (b) bij categorie 4 besloten de fulltext
niet in de index op te nemen. De toegangscategorie krijgt zo een plek in
de reguliere index die door Elasticsearch gebruikt wordt; die index wordt
door de Elasticsearch-proxy als PEP gebruikt. Voor de resolver komt een
aanvullende Elasticsearch-index die het toegangsniveau op file-niveau
vastlegt. Dezelfde categorie bepaalt tenslotte het opslagbeleid: alleen
categorie-0-objecten krijgen public-read op S3 (en zijn daarmee via het
CDN direct bereikbaar); objecten in categorie 1 en hoger staan non-public
en geven bij directe opvraging een `403`.

De bron voor de toegangscategorie is de RDF. De te realiseren
beheervoorziening om de toegangscategorie aan te passen werkt primair op
de RDF in het archief; de afgeleide waarden in ES volgen via de
indexeersoftware.

## De resolver

Alle toegang tot bestanden loopt via een resolver, vergelijkbaar met
SURA. De resolver geeft — afhankelijk van de **context** — op basis van
de URI van het opgevraagde document een URL terug. Voor publiek materiaal
is dat gewoon de URI zelf. Voor materiaal met beperkingen is dit, indien
toegang verleend mag worden, een tijdelijke URL die direct toegang geeft
tot de onderliggende bucket.

De resolver gebruikt hiervoor de resolver-index die door de PDP is
gemaakt. De **context** — de situatie waarin de aanroeper zich bevindt —
bepaalt de PEP zelf, uit twee betrouwbare signalen:

- het **client-IP**, waarmee studiezaal-verkeer wordt herkend aan een
  vaste allowlist (dit signaal komt van de serverzijde en kan de client
  niet zelf claimen);
- een **getekend cookie** met toegangsscopes: `consented` (na "ik stem
  in"), `granted:{ids}` (toegang tot specifieke categorie 3/4-records,
  uitgegeven via de beheervoorziening), of `granted:org:{uri}` /
  `granted:*` (organisatie-scopes, uitgegeven na federatieve login).

Contexten stapelen: wie op de studiezaal werkt én een grant heeft, mag
wat beide signalen toestaan. Zonder bruikbare context is het antwoord
gewoon `403`; bij uitval van de resolver blijft publiek materiaal (via de
CDN) bereikbaar, maar stopt alle beperkte levering.

De resolver en de Elasticsearch-proxy leven als endpoints in dezelfde
service (SURA); de contextbepaling hierboven is daardoor één gedeelde
functie, niet twee implementaties.

## Organisatie-toegang en delegatie

Naast toegang per record is er behoefte aan toegang per organisatie:
een medewerker van gemeente X krijgt toegang tot ál het materiaal dat
die gemeente gevormd heeft, en partijen als de brandweer tot alles.
Dat vraagt geen nieuw mechanisme — alleen ruimere grants:

- `granted:org:{uri}` dekt alle beperkte content waarvan de
  archiefvormer de eigen organisatie is; de indexer legt die
  archiefvormer-URI op elk document en elke bestandsrij als
  `access_org` vast, zodat de PEP-check één veldvergelijking blijft.
- `granted:*` dekt alle beperkte content (brandweer-achtige partijen).

De administratie daarvan ligt niet bij RAZU maar bij de organisatie
zelf. Elke organisatie beheert haar medewerkers al in een eigen
identity provider; de koppeling gebruikt uitsluitend de open standaard
OIDC, zodat de keuze van leverancier — Entra ID, Keycloak, SURFconext,
eigen open-source — per organisatie vrij is en de resolver het
verschil niet ziet. Wie inlogt bij de eigen organisatie krijgt van de
resolver dezelfde soort cookie met de bijbehorende organisatie-scope.
RAZU beheert alleen een kleine mapping van IdP-claim naar scope — wie
er precies in welke groep zit, is het eigen beheer van de deelnemende
organisatie.

## De Elasticsearch-proxy

Elasticsearch is voor gebruikers alleen via de proxy benaderbaar. De
proxy werkt als een regulier ES-interface maar bepaalt óók de context
(op dezelfde twee signalen als de resolver). Die context gebruikt hij,
samen met de in de zoekindex opgenomen toegangscategorie, om
fulltext-snippets wel of niet door te geven.

## Wat verandert er ten opzichte van nu

- **De snippetserver vervalt.** Zijn rol als PEP voor
  tekstfragmenten neemt de Elasticsearch-proxy over — goedkoper en efficienter, omdat
  Elasticsearch zelf highlight-fragmenten kan teruggeven in plaats van
  per request het ALTO-bestand te parsen.
- **SURA verandert van karakter.** De werking lijkt op die van de
  voorgestelde resolver, maar nu geeft SURA elke herkende URI
  onvoorwaardelijk een JWT mee dat het CDN controleert. In de nieuwe
  opzet checkt SURA eerst de toegangscategorie en de context, en geeft
  hij bij beperkt materiaal geen CDN-URI-met-token terug maar een
  tijdelijke presigned URL die direct naar de S3-bucket wijst. Er lopen
  dus geen bestandsbytes meer door SURA heen, en er staat geen token
  meer in de canonieke URI.
