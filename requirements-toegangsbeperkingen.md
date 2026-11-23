# Requirements: toegangsbeperkingen e-depot

Status: ontwerp, ter bespreking
Laatste update: 2026-11-20

## 1. Probleemstelling

Niet alle documenten in een e-depotsysteem zijn publiek toegankelijk. Sommige documenten hebben toegangsbeperkingen. Deze beperkingen zijn te verdelen in drie juridische categorieën:
- beperkingen vanuit de AVG, door aanwezigheid van persoonsgegevens
- beperkingen vanuit het auteursrecht, door aanwezigheid van auteursrechtelijk beschermde creatieve uitingen,
- beperkingen van de openbaarheid, zoals bijvoorbeeld op basis van belangen van de staat.

Voor iedere categorie geldt dat de beperking ook een einddatum heeft. Beperkingen vanuit de AVG hebben alleen betrekking op de persoonsgegevens van levende personen. Beperkingen vanuit het auteursrecht zijn normaliter actief tot 70 jaar na overlijden van de maker. Omdat er in het algemeen geen overlijdensdatum bekend is, worden door RAZU generieke termijnen gehanteerd. Ten aanzien van de AVG vervallen de beperkingen 82 jaar na creatie, ten aanzien van auteursrecht hanteert RAZU een termijn van 140 jaar na creatie. Ook archiefwettelijke openbaarheidsbeperkingen hebben een einddatum. Deze wordt vastgesteld en vastgelegd door de archiefvormer.

De toegangsvoorziening van het e-depot (in brede zin) moet deze beperkingen afdwingen. Om dit te kunnen realiseren is een aanpassing of uitbreiding op de bestaande architectuur nodig. De architectuur, de voorzieningen binnen de architectuur en de procedures rondom het systeem moeten bescherming bieden tegen onbevoegde toegang, zowel vanuit zeer gerichte aanvallen tot aan ongerichte harvesting.

Uitgangspunt is dat er gestreefd wordt naar een maximale toegankelijkheid van de documenten. Omdat het met de huidige techniek niet mogelijk is om geheel zeker te zijn van de aanwezigheid van de beperkende factoren, impliceert dit dat enig risico op het onbedoeld beschikbaarstellen als acceptabel wordt gezien.

De te ontwerpen en te realiseren aanpassingen in de architectuur moeten aan de volgende generieke eisen voldoen:
- ze moeten aansluiten op de huidige architectuur: de aanpassingen moeten compatibel zijn met de bestaande architectuur en niet leiden tot te grote veranderingen (zie 1.1)
- ze moeten aansluiten bij functionele eisen en wensen (zie 1.2)

Bovendien hanteren we het ontwerpprincipe van eenvoud boven complexiteit: binnen een te complexe oplossing worden eerder menselijke fouten gemaakt door gebrek aan overzicht, ook als de oplossing 'op papier' de betere is.

### 1.1. Bestaande architectuur

De bestaande architectuur van het RAZU e-depot volgt een gelaagd model bestaande uit:
- presentatielaag
- applicatielaag
- datalaag

Er wordt hierbinnen zo veel mogelijk gewerkt met vervangbare modulaire componenten, waar mogelijk open source en op basis van gangbare standaarden.

De datalaag bestaat uit een opslag op een lokale NAS en een complete replica daarvan op een externe S3-service. De publieke URIs van bestanden worden verzorgd door een Content Delivery Network (CDN).
Metadata wordt in de datalaag via 'sidecar'-bestanden in RDF (json-ld) opgeslagen, maar is ook beschikbaar in de applicatielaag via een triple store met behulp van SPARQL. Bovendien is er in de applicatielaag een zoekindex opgebouwd in een Elasticsearch-instantie waarin ook de tekst van documenten kan worden opgeslagen.

De presentatielaag wordt verzorgd door de Valeros-applicatie (https://github.com/Regionaal-Archief-Zuid-Utrecht/Valeros-RAZU). Valeros maakt gebruik van services uit de applicatielaag zoals de triple store en de zoekindex, maar bijvoorbeeld ook een IIIF-image-server voor het tonen van afbeeldingen, een service voor het genereren van PDF's, en een 'snippet'-service voor het leveren van tekstknipsels voor zoekresultaten (voor de gevallen waarin Elasticsearch deze niet biedt).

In de huidige opzet halen de ondersteunende services de vereiste bestanden direct op uit de S3-opslag. Zo zijn alleen 'public-read'- documenten nu beschikbaar.

In de bestaande architectuur is een voorziening 'SURA' die URIs kan vertalen naar een URL met JWT-token voor toegang tot het CDN. In de huidige opzet zijn echter geen tokens nodig voor toegang tot het CDN.

Toegangsbeperkingen worden in de RDF geadministreerd en zijn beschikbaar via de bestandsopslag én secundair via de triple store.

### 1.2. Functionele eisen en wensen

#### 1.2.1. Persistente URIs
Een uitgangspunt is dat we zo veel mogelijk werken met persistente URIs. Dit zowel voor de documenten in de datalaag, de metadata-entiteiten die geserveerd worden via de applicatielaag, als ook voor de presentaties van documenten en dossiers. *** TODO: also Resolvable****

Publiek toegankelijke documenten moeten met die persistente URI uit de datalaag opgevraagd kunnen worden.
Wenselijk is dat ook documenten die niet publiek toegankelijk zijn via de URI uit de datalaag opgevraagd kunnen worden (maar dat dan een noodzakelijke authenticatie- en autorisatiestap volgen).

#### 1.2.2. Gradaties in toegang tot de documenten
Wat betreft de toegang tot documenten uit de datalaag voorzien we, te specificeren per document, 4 mogelijke niveaus van toegang:

0. online en publiek toegankelijk (TODO: KB stuff license - explain)
1. online, maar enkel toegankelijk, via een aangevraagde kopie voor persoonlijk gebruik en na instemming met de voorwaarden
2. toegankelijk via de voorziening in de RAZU-studiezaal
3. online, maar enkel toegankelijk voor specifieke gebruikers, na aanmelding

Deze categorieën gelden per document. Eventuele beperkingen op metadata (zie 1.2.3) kunnen daarnaast ook op dossierniveau spelen.

Binnen iedere categorie streven we naar een maximaal laagdrempelige toegang, binnen de grenzen van de gestelde categorie.

Van de categorieën volgt hieronder een nadere uitleg.

##### 0. Publiek toegankelijk
Deze categorie betreft documenten zonder beperkingen, of waarvan de beperkingen al verlopen zijn. Het is vermeldenswaardig dat archiefvormers van documenten met beperkingen soms een afgeleide hebben gemaakt die geen beperkingen meer kent. Wenselijk is dat de metadata op documentniveau deze relatie tussen het originele document met beperkingen en de afgeleide toegangskopie vastlegt. De gebruiker moet op niveau van de presentatielaag op het bestaan van de publiek toegankelijke afgeleide gewezen worden.

Materiaal dat publiek toegankelijk is mag geharvest worden, maar het is nodig om begrenzingen te kunnen opleggen om te voorkomen dat de dienstverlening aan reguliere gebruikers onder de te intensieve harvesting leidt. In de bestaande opzet van het e-depot kan dit al via het CDN worden afgedwongen.

##### 1. Persoonlijke kopie
Een typisch voorbeeld van een document dat als persoonlijke kopie na instemming met de voorwaarden beschikbaar kan worden gemaakt zijn de bouwtekeningen uit bouwdossiers. Hier gelden mogelijk auteursrechtelijke beperkingen, maar met als uitzondering dat het toegestaan is een kopie te maken voor persoonlijk gebruik, mits deze niet verder gedeeld wordt en bijvoorbeeld ook niet gebruikt wordt om de constructie na te bouwen (zie https://www.kvan.nl/wp-content/uploads/2024/03/315.2-Kennisdocument-Bouwdossiers-KVAN-2024.pdf).

De nadruk ligt op het **downloaden** van de persoonlijke kopie; het online bekijken van het document in de viewer is secundair. Het is daarom acceptable dat herhaalde instemming na verloop van de sessie/token (bijvoorbeeld elk uur) nodig is.

Overigens kunnen bij deze bouwtekeningen ook AVG-gerelateerde beperkingen gelden, maar de aanname is dat dit niet in die mate speelt dat ze het aanleveren van een persoonlijke kopie verhinderen. Dit zal bij de materiaalvoorbereiding (pre-ingest) met de beschikbare middelen geverifieerd moeten worden.

Een veelvoorkomende aanpak bij archiefinstellingen is dat gebruikers, na instemming met de voorwaarden, zich met hun e-mailadres aanmelden en daarna een link krijgen om de documenten te downloaden, al dan niet na handmatige verificatie (?). Van belang is bovenal dat de toegangsroute niet misbruikt kan worden voor grootschalige geautomatiseerde en ongeauthoriseerde harvesting. Een route via e-mail lijkt een geschikte, maar ook niet de meest laagdrempelige aanpak 
Onder dat misbruik valt nadrukkelijk ook het geautomatiseerd doorlopen van de instemmingsflow door bots (sessie starten → instemmen → downloaden, in een loop). De categorie-1-route moet daarom effectieve anti-automatiseringsmaatregelen bevatten (proof-of-work, honeypot, rate limiting, IP-blocking, anomaliedetectie); de concrete maatregelen zijn uitgewerkt in het architectuurdocument (§A.3, §7).

##### 2. Toegang via de studiezaal
Een typisch gebruiksgeval voor toegang via de studiezaal zijn documenten die in verband met beperkingen op auteursrecht of privacy niet publiek toegankelijk zijn, maar wel toegankelijk voor bezoekers in de studiezaal. In de studiezaal hoeven gebruikers zich niet individueel bekend te maken; er kan anoniem gebruik gemaakt worden van een vrij beschikbare terminal (en kunnen daar ook persoonlijke kopieën worden gemaakt via printen?).

In de huidige situatie bij RAZU zijn sommige kranten niet publiek beschikbaar vanwege auteursrechtelijke beperkingen. Er is hiervoor nu nog geen alternatieve toegang in de studiezaal opgezet.

##### 3. Toegang voor specifieke gebruikers

Typisch gebruiksgeval voor toegang voor specifieke gebruikers zijn documenten die in verband met beperkingen op de openbaarheid niet toegankelijk zijn. Alleen na verzoek én instemming vanuit de archivaris kan er (tijdelijk) toegang verleend worden tot specifieke documenten.

Dit kan ook spelen bij documenten met andersoortige beperkingen. Zo zal voor het bekijken van de aanvragen voor bouwvergunningen waar persoonsgegevens op te vinden zijn, om toegang gevraagd moeten worden.

Een ander gebruiksgeval in deze categorie is waarbij medewerkers vanuit een aangesloten gemeente (archiefvormer) vanuit hun functie toegang moeten kunnen krijgen tot specifieke selecties van documenten. Een typisch voorbeeld is een medewerker van de brandweer die toegang moet kunnen krijgen tot alle bouwtekeningen in een gemeente.

(NB: is de toegang dan per gemeente of zijn ook andere selecties nodig? Bijvoorbeeld toegang tot alle documenten van een bepaald type (ongeachte archiefvormer?), of toegang tot alle documenten ongeacht vorm of type?)

Een verleende toegang is altijd scope-specifiek: zij geldt uitsluitend voor de documenten of dossiers waarvoor zij is verleend. Binnen zo'n scope kunnen documenten met een andere basiscategorie (1 of 2) vallen; voor de bevoegde actor geldt dan de toegang zoals die via categorie 3 is verleend — het geven van instemming voor gebruik als persoonlijke kopie, of een studiezaalbezoek is daar in dat geval daarvoor niet vereist. Tijdelijke verleningen kennen een expliciete einddatum en verlopen automatisch.

###### Actoren en toegangsmatrix

Bij de categorieën spelen de volgende actoren een rol:

- **Online bezoeker** — gebruikt de publieke zoek- en presentatievoorziening zonder aanmelding; kan wel instemmen met de voorwaarden voor categorie 1; die instemming geldt per dossier.
- **Studiezaalbezoeker** — anonieme gebruiker van een vrij beschikbare terminal in de RAZU-studiezaal; geen individuele aanmelding, maar vereist nog steeds instemming voor toegang tot categorie 1.
- **Geautoriseerde bezoeker** — individueel aangemelde gebruiker die na verzoek en instemming van de archivaris (tijdelijke) toegang heeft gekregen tot specifieke documenten.
- **Medewerker deelnemende organisatie** — aangemeld via de eigen organisatie (bijvoorbeeld een gemeente of de lokale brandweer); heeft vanuit zijn functie toegang tot een vastgelegde selectie van documenten.
- **Archivaris / beheerder** — beheert de toegangsbeperkingen in de bron (RDF-sidecars) en verleent toegang aan specifieke gebruikers; treedt niet op als eindgebruiker van de voorziening.
- **Geautomatiseerde gebruiker** — harvesters en zoekmachine-crawlers; heeft toegang tot publiek materiaal binnen opgestelde limieten.

De matrix heeft betrekking op toegang tot documenten; de metadata-beperkingen uit 1.2.3 staan daar los van. De kolomkop geeft de voorwaarde van de categorie aan: geen voorwaarden (0), instemming met de voorwaarden persoonlijke kopie (1), aanwezigheid in de studiezaal (2), of een individueel verleende toegang (3).

| Actor | 0 publiek | 1 persoonlijke kopie | 2 studiezaal | 3 op verzoek |
| --- | --- | --- | --- | --- |
| Online bezoeker | ✓ | ✓ | – | – |
| Studiezaalbezoeker | ✓ | ✓ | ✓ | – |
| Geautoriseerde bezoeker | ✓ | ✓ | – | verleende documenten |
| Medewerker deelnemende organisatie | ✓ | ✓ | – | verleende selectie |
| Geautomatiseerde gebruiker | ✓, binnen begrenzingen | – | – | – |

De matrix beschrijft per actor het **typische gebruik**: welke voorziening de actor benut om toegang te verkrijgen. Hij is geen verbod op combinaties — wie aan meerdere voorwaarden voldoet, krijgt de ruimste combinatie. Zo raadpleegt een gebruiker met een verleende toegang die zich in de studiezaal bevindt ook categorie-2-documenten, en een studiezaalbezoeker kan óók instemmen met de voorwaarden voor categorie 1.

#### 1.2.3. Gradaties in toegang tot de metadata

De beperkingen vanuit de AVG, de archiefwettelijke openbaarheidsbeperkingen en deels ook die ten aanzien van de auteursrechten kunnen ook gevolgen hebben voor het al dan niet kunnen tonen van specifieke metadata-velden. Waar de categorieën uit 1.2.2 per document gelden, spelen de beperkingen op metadata ook op dossierniveau: de vindbaarheid en toonbaarheid van een dossier als geheel kan beperkt zijn. Er zou ook gesteld kunnen worden dat zelfs het kunnen vinden van documenten of dossiers op basis van een zoekvraag kan leiden tot een overtreding van de AVG of van de openbaarheidsbeperkingen.

Voor de krantencollectie geldt dat het tonen van een 'snippet' of tekstknipsel van de volledige tekst van een krant, zoals beschikbaar gesteld via de zoekmachine, een overtreding zou kunnen zijn van het auteursrecht. Van deze kranten wordt in een lijst met zoekresultaten dan ook geen knipsel getoond. Overigens is deze aanpak feitelijk onnodig streng: alle bestaande auteursrechtelijke beperkingen stammen van bezwaar van makers van beeldmateriaal, dat uit de aard van de materie niet als een tekstknipsel kan worden gerepresenteerd.

Voor bijvoorbeeld bouwdossiers geldt dat ze persoonsgegevens bevatten, specifiek met betrekking tot de aanvrager van de bouwvergunning. Deze persoonsgegevens mogen niet zichtbaar zijn in de metadata van de dossiers (mag er wel op gezocht worden?)


#### 1.2.4. Beheer / overig

Het instemmen met de voorwaarden voor een persoonlijk kopie heeft betrekking op alle documenten voor het betreffende dossier, binnen de betreffende categorie.

Het verlenen van toegang moet met zo min mogelijke administratieve stappen kunnen gebeuren.

Beheer van toegang voor gebruikers met een verleende toegang (categorie 3) geschiedt zo veel mogelijk decentraal, bijvoorbeeld via de systemen van de organisaties die in RAZU participeren. Zo'n organisatie beheert dan ook zelf wíé haar medewerkers zijn — RAZU beheert geen accounts van medewerkers.
Daarnaast moet RAZU zelf tijdelijke toegangen kunnen verlenen aan gebruikers die niet via een deelnemende organisatie komen. Ook dat is verlenen van toegang (met einddatum), geen gebruikersadministratie: er is geen account, de aanmelding gebeurt met een uitgereikt credential.

Er is één bron van waarheid voor de toegangsbeperkingen: de RDF-sidecars. Voorkomen moet worden dat toegangsbeperkingen in meerdere systemen worden beheerd of dat administraties in verschillende systemen langere tijd uit de pas kunnen gaan lopen.

De toegang tot documenten, of een bredere selectie van documenten, moet in minder dan een dagdeel effectief aangepast kunnen worden.

Het laten verlopen van toegangsbeperkingen moet automatisch kunnen gebeuren, minstens op jaarlijkse basis.

De formele administratie van het verleningsproces voor tijdelijke toegang (aanvraagdossiers, besluitvorming, archiefverantwoording) is nu buiten scope. Het register met verleende toegangen dat de toegangsvoorziening bij de raadpleging nodig heeft, is daarentegen essentieel; de aanvraag- en uitgifteflow (verlening via een uitgereikt credential) is uitgewerkt in het architectuurdocument.

Rapportage-functionaliteit?

Daarnaast is signalering op verdacht geautomatiseerd gebruik gewenst: analyse van het resolver-auditlog moet patronen van geautomatiseerde harvesting (veel sessies met telkens één dossier, abnormale request-frequenties) leidend tot een melding, zodat tijdig kan worden ingegrepen (zie architectuur §7).
