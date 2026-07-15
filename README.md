# Early Bird scanner

Automatisk scanner som henter pressemeldinger/børsmeldinger for et
selskapsunivers (se `config/watchlist.json`), filtrerer for relevans, og
sender et utkast (overskrift + kommentar, i SEBs Early Bird-stil) på e-post
2 ganger hver morgen (07:32 og 08:02 Oslo-tid).

## Hvorfor GitHub Actions (ikke Claude Code-økten)

Claude Code-miljøet dette ble bygget i har ingen generell internettilgang
(kun Anthropic + pakkebrønner er tillatt), så all henting av nyheter må skje
et sted med ordentlig nettilgang. GitHub Actions-runnere har full
internettilgang som standard, og cron-planlegging der er mer robust enn å
stole på en våknende chat-økt. Se `.github/workflows/early-bird.yml`.

## Oppsett (secrets)

Gå til **Settings → Secrets and variables → Actions** i dette repoet og legg inn:

| Secret | Hvor du finner den |
|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys |
| `RESEND_API_KEY` | resend.com → API Keys |
| `FROM_EMAIL` | En adresse på et domene du har **verifisert** i Resend (resend.com/domains). Uten verifisert domene kan Resend kun sende til kontoeierens egen adresse. |

Mottaker er for øyeblikket kun `jonasaulie@gmail.com` (`src/emailer.py`
`DEFAULT_RECIPIENTS`), siden Resend uten et verifisert domene bare kan sende
til kontoeierens egen adresse. `jonas.aulie@seb.no` ble testet (bekreftet
403 fra Resend: "You can only send testing emails to your own email
address") og er bevisst tatt ut igjen — videresending gjøres manuelt i
stedet. **Ikke** verifiser `seb.no` i Resend — det er SEB sitt
bedriftsdomene og krever DNS-endringer bare IT-avdelingen bør gjøre. Vil du
legge til `jonas.aulie@seb.no` igjen: verifiser et domene du faktisk eier
selv i Resend, sett det som `FROM_EMAIL`, og legg adressen til i
`DEFAULT_RECIPIENTS`.

**Sikkerhetsnotat:** Resend-nøkkelen som ble limt inn i en tidligere chat bør
regenereres i Resend-dashbordet før den tas i bruk her, siden den har stått
i klartekst i en samtale.

## Newsweb (Oslo Børs)

Newsweb er en React SPA — henter man `newsweb.oslobors.no` direkte med
`requests.get()` får man bare et tomt HTML-skall. Den faktiske dataen hentes
slik (funnet via en Playwright-nettverkstrace, se
`scripts/probe_newsweb_playwright.py`):

1. Appen henter runtime-config fra `https://newsweb.oslobors.no/urls.json`,
   som oppgir den ekte API-basen: `https://api3.oslo.oslobors.no`.
2. Meldinger per selskap hentes fra
   `https://api3.oslo.oslobors.no/v1/newsreader/list?issuer=<TICKER>`.

`src/fetch_newsweb.py` bruker dette endepunktet direkte og er verifisert
fungerende på en ekte GitHub Actions-kjøring. Newsweb dekker ikke alt en
bedrift publiserer (bl.a. ikke-informasjonspliktige pressemeldinger), så
`src/main.py` henter alltid også selskapets egen IR-side i tillegg.

List-endepunktet over gir bare tittel, ikke selve meldingsteksten -- det
gjorde tidlige kommentarer generiske/feil (f.eks. «no transaction details
were disclosed» på en melding som faktisk oppga kjøpesum og earn-out).
`src/fetch_newsweb.py` henter nå i tillegg full meldingstekst per sak fra
`.../v1/newsreader/message?messageId=<id>` (funnet via
`scripts/probe_newsweb_message_body.py`), så drafteren har de faktiske
tallene å jobbe med.

**Viktig: `list?issuer=X` uten datoparametre kan stille returnere tomt selv
når selskapet har publisert nylig.** Oppdaget da Equinor og NorAm Drilling
sine sanne saker (bekreftet i den ekte Early Bird-utgaven) ga 0 treff fra
det udaterte kallet, mens samme kall med `&fromDate=...&toDate=...` ga
ekte data (`scripts/probe_newsweb_list_size.py`). Dette virker som en aktiv
API-ustabilitet, ikke noe vi kan stole på. `fetch_issuer_messages()` sender
derfor alltid med et eksplisitt 10-dagers datospenn
(`LOOKBACK_DAYS` i `fetch_newsweb.py`) i stedet for å stole på
standardoppførselen.

**Viktig: `newsweb_issuer`-koden må være verifisert riktig, ellers får du
feilkoblet innhold.** Oppdaget via `scripts/probe_newsweb_issuer_mismatch.py`:
fire ticker-koder i watchlisten (`KOMA` for Kongsberg Maritime, `SOMAR` for
Solstad Maritime, `SED` for SED Energy Holdings, `AKA` for Akastor) var ikke
gjenkjent av API-et, som da falt tilbake på en generisk/urelatert 69-post
liste (samme respons for alle fire, med et helt annet selskap øverst) i
stedet for et tomt resultat. Dette kunne ha ført til at en reell børsmelding
fra ett selskap ble sendt ut merket med et helt annet selskaps navn. Alle
fire er nå satt til `newsweb_issuer: null` (de dekkes fortsatt via sin
`ir_url`) inntil noen finner og verifiserer de faktiske Newsweb-tickerne
deres — for Kongsberg Maritime er det mulig det ikke finnes en egen
børsnotering i det hele tatt (det er en forretningsenhet under Kongsberg
Gruppen ASA). Bekreftet korrekte: `EQNR`, `TGS`, `NEL`, `NORAM`, `SUBC`,
`AKRBP`, `VAR`.

## Recency / kun siste døgn

Kun saker publisert innenfor tidsvinduet (siden 08:30 Oslo dagen før, se
under) slippes gjennom. For sider uten RSS-feed scrapes overskrifter, og
`src/fetch_ir.py` prøver hardt å finne en publiseringsdato ved siden av hver
overskrift (dato i selve artikkel-URL-en, `<time datetime>`/`data-date`-
attributter, eller en datostreng i overskriftens kort/rad — også norske
datoer som «8. juli 2026»). **Klarer vi ikke å datofeste en scrapet
overskrift, droppes den.** Det er med vilje: tidligere lente koden seg kun på
dedup, så første gang en ny IR-URL begynte å virke ble hele forsiden med
*gamle* overskrifter sendt ut som om de var nye (det var det som sendte tre
gamle SED Energy-saker). Det koster potensielt en sjelden udatert sak, men
sparer både feilsendinger og token-bruk.

Datotolkning respekterer regional konvensjon: skråstrek-datoer (`7/8/2026`)
tolkes måned-først (amerikansk IR-side-konvensjon), punktum-datoer
(`08.07.2026`) tolkes dag-først (europeisk/norsk konvensjon), ISO
(`2026-07-08`) er alltid entydig. Før dette ble alle ikke-ISO datoer tolket
dag-først, som stille kunne bytte om dag og måned på amerikanske
pressemeldinger datert forbi den 12. i måneden.

## Ingen persistent dedup -- kun tidsvinduet avgjør (bevisst valg)

Det finnes ingen «allerede sendt»-sperre eller state-fil av noe slag.
`src/main.py` sender ALT som er innenfor recency-vinduet (siden 08:30
Oslo-tid dagen før, eller fredag 08:30 på mandager) til relevansfilteret
hver eneste gang jobben kjører — uavhengig av om samme sak ble sendt i en
tidligere kjøring. I praksis betyr det:

- 07:32- og 08:02-kjøringen samme dag deler samme vindu, så begge mailene
  inneholder de samme relevante sakene (pluss ev. noe helt nytt som kom til
  i mellomtiden) — ingen av dem er en "kun det som er nytt siden sist"-mail.
- En sak funnet f.eks. kl. 09:30 en dag kan også dukke opp i begge
  kjøringene neste dag også, siden den fortsatt er innenfor det vinduet.
  Den faller naturlig ut når vinduet ruller videre (typisk etter 1–2 dager).

Dette er et bevisst valg: en sak skal aldri kunne bli "brukt opp" av en
tidligere kjøring (manuell test eller reell) og dermed mangle fra en
kjøring den egentlig hører hjemme i. Prisen er at samme sak kan sendes
flere ganger på rad, og at token-kostnaden er høyere enn med dedup (samme
kandidatmengde re-evalueres av modellen på hver kjøring i stedet for bare
delta) — vurdert som en god byttehandel mot risikoen for at noe reelt
mangler. Som en ekstra bonus-effekt forsvinner også den gamle
feilkategorien der en enkelt LLM-feilvurdering kunne begrave en sak
permanent (det trengte en egen dedup-unntaksregel for Newsweb-saker før;
den regelen er nå overflødig siden det ikke finnes noen "sett"-liste å bli
feilaktig begravet i).

Hvis noe fortsatt mangler: `src/main.py` logger fortsatt hver kandidat som
ble hentet (selskap, dato, tittel) og alt relevansfilteret droppet — les
run-loggen på GitHub Actions for å se nøyaktig hva som skjedde med en
konkret sak, i stedet for å måtte skrive et eget probe-script.

**Unntak lagt til 15. juli 2026:** når samme selskap har to kilder for
samme sak — typisk Newsweb (alltid presist klokkeslett) og selskapets egen
nyhetsside (ofte bare en bar dato, se avsnittet under om "hele dagen
teller") — fikk den bar-dato-kopien noen ganger én ekstra dags levetid
utover det den presise kopien selv ville fått, fordi "hele dagen
teller"-fallbacken (se under) ikke vet at det egentlig var samme hendelse.
Bekreftet live: en DOF Group-kontraktstildeling, publisert før 08:30 og
korrekt ekskludert via sin presise Newsweb-tid, dukket likevel opp igjen
neste morgen via sin bar-dato dof.no-duplikat. `collect_candidates()`
dropper nå bar-dato-kandidaten per selskap når en presist tidsstemplet
søsken-kandidat allerede dekker samme kalenderdato (`_dedupe_bare_date_duplicates`
i `src/main.py`) — dette er ikke persistent dedup på tvers av kjøringer
(fortsatt ingen state-fil), bare en sammenslåing av to kilder for samme
hendelse innenfor én og samme kjøring, før recency-filteret. Selskaper uten
Newsweb-dekning (typisk amerikanske/utenlandske navn som kun har en
IR-side) er upåvirket — der finnes det ingen presis søsken-kandidat å
sammenligne med, så "hele dagen teller"-fallbacken fungerer akkurat som før
(det den ble laget for: SLB/Baker Hughes-tilfellet over).

## Klokkeslett i datofeltet, ikke bare kalenderdato

`fetch_ir.py` fanger nå opp et klokkeslett rett etter datoen i en
overskrift (f.eks. Equinors "10 July 2026|08:00 (CEST)Equinor's second
quarter..."), i stedet for å bare beholde datoen og stille anta
midnatt. Uten dette ble en sak reelt publisert kl. 08:00 — 30 minutter
før selve 08:30-grensen — behandlet som "hele dagen teller" og dukket
opp en dag den ikke skulle. Bekreftet live: en Equinor-sak fra kl. 08:00
lørdag/fredag dukket opp i en kjøring som burde ha kuttet den. Rene
dato-uten-klokkeslett-kilder (fortsatt det vanlige for de fleste
IR-sider) er upåvirket og bruker samme "hele dagen teller"-fallback som før.

## Token-bruk / kostnad

Token-kostnaden er Anthropic API-kostnad og henger **ikke** sammen med hvor
koden kjøres — å flytte kjøringen til Google Cloud, Colab e.l. endrer ingenting
på dette (det bytter bare gratis-runner). Det som styrer token-bruken er hvor
mange nyhetssaker som sendes til modellen per kjøring. Den store innsparingen
er derfor recency-filteret over: før datofiltreringen ble hundrevis av gamle,
udaterte overskrifter sendt til modellen hver kjøring; nå sendes bare det som
faktisk er datofestet innenfor døgnet — typisk en brøkdel. Vil du kutte mer
kan man bytte drafting-modellen i `src/draft.py` (`MODEL`) til en billigere
Claude-modell, på bekostning av litt tekstkvalitet.

## JS-rendrede IR-sider (headless-nettleser-fallback)

En vanlig `requests.get()` ser bare skallet en ren JavaScript-app (SPA)
sender ut før JavaScript kjører. `src/fetch_ir.py` prøver derfor, hvis RSS-feed
og vanlig HTML-scrape enten finner null treff eller bare finner treff uten
noen ekstraherbar dato, å rendre siden med en ekte (headless) Chromium-
nettleser via Playwright og kjøre samme scrape-logikk på det rendrede
resultatet (`_fetch_via_headless_browser`). GitHub Actions-workflowen
installerer Chromium (`playwright install --with-deps chromium`) i hvert
kjøre.

Fallback-en trigges ved null *daterte* treff (ikke bare null treff totalt) —
dette fanger opp sider som svarer 200 OK på en vanlig request med reelt
innhold, men der innholdet bare er navigasjonslenker (udaterte) fordi selve
overskriftslisten lastes inn via JS etter sidelasting (bekreftet for Baker
Hughes, se under). Rendring prøver på nytt én gang med lengre ventetid før
den gir opp, siden en fast ventetid av og til er for kort. Sjekk loggen for
`[fetch_ir] NOTE: ... needed the headless-browser fallback` for å se hvilke
selskaper som faktisk trengte den, og `WARNING: headless browser fetch
failed` hvis selv det ikke klarte å hente noe.

## Kjente begrensninger

Full gjennomgang av alle ~58 selskaper (`scripts/probe_watchlist_coverage.py`,
juli 2026) viste 52/58 fungerende. De resterende:

- **Transocean** — `investor.deepwater.com` hadde et server-side problem
  (`net::ERR_HTTP2_PROTOCOL_ERROR`/timeout, både med vanlig request og
  headless). Fikset: byttet til `www.deepwater.com/news/`, som svarer 200 OK.
- **SBM Offshore** — scrapet feil URL. `/newsroom/` er bare en landingsside
  uten faktiske overskrifter (kun navigasjonsmeny i markupen, selv rendret);
  den ekte pressemeldingslisten ligger på `/investors/press-releases/`, som
  ble funnet ved å dumpe alle lenker på siden. Fikset.
- **Baker Hughes** — fikset. To separate problemer: (1) feil URL —
  `bakerhughes.com/company/news` er en ren JS-app under inkonsekvent
  bot-beskyttelse, mens den faktiske pressemeldingslisten ligger på en helt
  separat IR-plattform-subdomene, `investors.bakerhughes.com/news`, som svarer
  200 OK på en vanlig `requests.get()`. (2) en generell ordningsbug i
  `_scrape_listing()` — koden brøt ut av lenke-skanningen ved de første 15
  treffene i DOM-rekkefølge, så på sider der navigasjonsmenyen (alltid udatert)
  kommer før de ekte overskriftene i HTML-en, ble alle reelle, daterte
  overskrifter presset ut før de i det hele tatt ble nådd. Fikset ved å samle
  alle kandidater uten tidlig brudd og sortere daterte treff først. I tillegg
  gikk `fetch_company_news()` for tidlig ut med udaterte scrape-treff i stedet
  for å falle videre til headless-nettleseren — fikset til å prøve headless
  når scrapet finner null *daterte* treff, ikke bare null treff totalt.
  Bekreftet: gir nå ekte daterte overskrifter i produksjon. (3) Oppdaget 15.
  juli 2026: en reelt gammel sak (Baker Hughes/Twenty20 Energy gassturbin-
  ordre, faktisk publisert 11. februar 2026) dukket likevel opp i en
  15. juli-kjøring, tilsynelatende med en feilaktig fersk dato. Årsak:
  `_extract_published()` utvider søket til besteforelder-noden når dato ikke
  finnes i selve lenken/kortet — på en side der den noden omslutter *flere*
  overskrifter (en delt liste-wrapper, ikke ett enkelt kort), kunne dette
  plukke opp en *annen*, ferskere overskrifts dato i stedet for den faktiske
  sakens egen. Fikset: utvidelsen stopper nå så snart scope-noden inneholder
  mer enn denne ene overskriftens egen lenke, i stedet for å anta at en
  hvilken som helst dato funnet i en videre node hører til akkurat denne
  saken.
- **Chevron** — fikset. Feil URL — den konfigurerte lenken hadde et
  query-parameter (`?contenttype=press%20release`) som ga en side med null
  daterte overskrifter; den enklere `www.chevron.com/newsroom` gir 20/20
  daterte kandidater inkludert ferske saker.
- **Saudi Aramco** — direkte scraping av `aramco.com` er fortsatt
  uløselig: både vanlig `requests.get()`, en ekte headless nettleser, OG et
  tredjeparts reader-proxy-verktøy (r.jina.ai) feiler alle konsekvent med
  `net::ERR_HTTP2_PROTOCOL_ERROR`/403 (`scripts/probe_aramco_subsea7.py`,
  `probe_aramco_subsea7_alt_sources.py`) — et mønster typisk for en WAF som
  blokkerer datasenter-IP-adresser på nettverksnivå, ikke noe en bedre
  scraping-teknikk kan løse. **Løst likevel** via en annen vei: Google
  News- og Bing News RSS kjører på Googles/Microsofts egen infrastruktur,
  ikke Aramcos, så blokkeringen treffer dem ikke — bekreftet live til å gi
  ekte, relevante saker (kontraktstildelinger, rørledningsprosjekt-
  oppdateringer) som Aramcos egen side blokkerer oss fra å se direkte. Lagt
  til som fallback-kilde (`src/fetch_news_aggregator.py`,
  `news_aggregator_query` i watchlist.json) kun for Aramco. Støyere enn en
  ren pressemeldings-feed (blander inn tredjeparts analyse/kommentarer),
  men det eksisterende relevansfilteret håndterer det fint — bekreftet
  live: en urelatert sak om et statsbesøk som nevnte Aramco i forbifarten
  ble korrekt droppet, mens ekte kontraktnyheter er nøyaktig den typen
  saker filteret er bygget for å beholde.
- **Subsea7** — samme type IP-rykte-blokkering som Aramco (bekreftet: alle
  testede URL-er serverer en identisk JS-bot-utfordringsside, `<title>
  Challenge Validation</title>`, som aldri løser seg selv etter 30
  sekunders vent og med `navigator.webdriver` spoofet til `false` — se
  `scripts/probe_subsea7_challenge.py`). Samme Google/Bing News RSS-vei
  virker også her (bekreftet: fant ekte saker om Saipem-fusjonen, ny CEO,
  kontraktstildeling), men er **ikke** lagt til som fallback siden
  selskapet uansett er fullt dekket via Newsweb (`SUBC`) — ville bare gitt
  duplikat-risiko for null gevinst. Kan legges til senere hvis det viser
  seg at Newsweb mangler noe (f.eks. fusjonsnyheter som kommer via Saipems
  italienske børs snarere enn Oslo Newsweb).

- **WAF-blokkering (403):** Weatherford, Chevron, BP, Ørsted har
  WAF/Akamai-beskyttelse som kan avvise en vanlig `requests.get()` uansett
  User-Agent. `fetch_ir.py` prøver nå headless-nettleseren (samme mekanisme
  som for JS-rendrede sider) også når den vanlige forespørselen feiler med
  403 — en ekte nettleser har en ekte TLS/JS-fingeravtrykk som ofte kommer
  forbi enklere botdeteksjon. Bekreftet virker for Weatherford. Ikke
  garantert mot alle WAF-er (Akamai Bot Manager kan i prinsippet fortsatt
  oppdage automatisering), men verdt å prøve før man gir opp helt.
- Noen få selskaper i `config/watchlist.json` mangler fortsatt `ir_url`
  (`null`) — spesielt et par mindre norske Euronext Growth-selskaper.
- `scripts/probe_urls.py`, `scripts/probe_newsweb_playwright.py`,
  `scripts/probe_bakerhughes.py`, `scripts/probe_watchlist_coverage.py` og
  `scripts/discover_ir_urls.py` er beholdt som permanente feilsøkingsverktøy
  — kjør `probe_watchlist_coverage.py` via en midlertidig
  workflow_dispatch-jobb når som helst for å få en fersk statusliste over
  hvilke selskaper som faktisk gir treff akkurat nå.

## Relevanskriterier (hva som tas med / droppes)

`src/draft.py` sitt system-prompt har en eksplisitt kriterieliste. Grunn-
spørsmålet er: «ville dette endret hvordan en forvalter tenker om aksjen,
en peer eller sektoren i dag?» — altså value-add nyhetsflyt som kan bevege
en kurs.

Filteret er bevisst satt til å heller ta med for mye enn for lite — det er
verre å miste en sak analytikeren trengte enn å ha med én ekstra linje han
skummer forbi på to sekunder.

**Tas MED:** (a) kontrakter/tildelinger/ordre/tenders/rammeavtaler/LOI/MOU
— uansett størrelse, også uten oppgitt verdi hvis omfang/motpart er
vesentlig; (b) M&A og porteføljegrep (oppkjøp, frasalg, fusjoner, farm-in/
out, vesentlige eierandelsendringer); (c) field developments / E&P-
milepæler (FID, funn, first oil/gas, produksjonsstart, reserveoppdateringer,
lisensrunder, PUD-godkjenning); (d) kapital-/balansegrep (tilbakekjøp,
utbytteendring, emisjoner, refinansiering, rating); (e) **kvartalstall,
trading updates og driftsoppdateringer som inneholder faktiske tall**
(produksjonsvolum, inntekt/EBITDA, prisoppnåelse, rigg-/flåtetall, ordre-
reserve/backlog, guiding) — tas med uansett om tallene er «overraskende»
eller ikke, en forvalter vil ha kvartalstallene uansett (f.eks. «Vår Energi:
Second quarter 2026 trading update» eller «OKEA second quarter 2026 trading
update» — har den tall, er den med); (f) rigg/OSV-markedsdata (rater,
kontrakter, utnyttelse, nybygg/salg); (g) regulatorisk/juridisk/politisk med
reell finansiell effekt (OPEC, sanksjoner, bøter, skatt); (h) store
driftsforstyrrelser (utfall, force majeure, streik); (i) sektor/makro selv
uten ett navngitt selskap.

**Droppes (holdes bevisst smal):** kun rene møteinnkallinger uten tall —
«Invitation to Q2 2026 results presentation», «save the date»,
finanskalender — altså null datapunkter. Har saken ett eneste konkret tall,
er den IKKE i denne kategorien, den hører til (e) og skal med. Utover det:
rutinemessige primærinnsidemeldinger og flaggemeldinger (med mindre uvanlig
store); aksjekapital-/stemmerett-administrasjon, GF-innkallinger og
administrative filinger; mindre personalendringer (under C-nivå); generisk
ESG/PR/markedsføring/sponsing; duplikater av samme sak; rutinemessig
skipsfarts-/eksportvolum-omtale i handelspressen (havnelasting,
"eksporten nær maksimalnivå", en nedstrøms kjøper som bestiller en last) som
ikke er selskapets egen kontrakt/tildeling, og som typisk siteres til
anonyme «sources» i stedet for en selskapsmelding — selv om det tracked
selskapets navn står i overskriften. (Lagt til 15. juli 2026 etter to reelle
Aramco-saker av nettopp denne typen: havnelasting ved Yanbu og Zhenhuas
lastbestilling ved en JV-raffineri — begge uten noen selskapsmelding fra
Aramco selv.)

Ved tvil: ta saken MED. Det har skjedd to ganger at filteret var for
strengt og droppet noe det ikke skulle (TGS' salg til Enverus, og senere
Vår Energi/OKEA sine trading updates) — kriteriene over er skrevet for å
unngå akkurat det, med eksplisitt bias mot inklusjon.

## Drafting-stil

`src/draft.py` sitt system-prompt inneholder også ekte eksempler fra tidligere
Early Bird-utgaver (format, informasjonstetthet, når man avslutter med en
kort vurdering som "Neutral for Equinor." eller "Share price positive.").
Oppdater few-shot-eksemplene der om stilen bør justeres videre.

Gjeldende regler (håndhevet i system-promptet):
- **Tone**: nøytral, faktatett. Ingen adjektiver eller fyllord ("impressive",
  "notably" osv.) — la tallene og fakta bære innholdet.
- **Setningsoppbygning**: tidsangivelse → konkret hendelse → tall/kontekst,
  i den rekkefølgen både innad i setninger og gjennom avsnittet.
- **Overskrift**: `Selskap (Rec) – kort beskrivelse`. Har vi ikke dekning på
  selskapet (recommendation er null), droppes parentesen helt.
- **Lengde**: typisk 3–6 setninger, men det er et mål, ikke et hardt tak i
  noen retning — flere setninger hvis kilden faktisk har nok substans til at
  en forvalter eller megler trenger det, færre (ned til én setning) hvis
  kilden ikke har mer å si. Hver setning skal være value-add; ingen
  fyllsetninger som bare gjentar overskriften.

**Artikkeltekst, ikke bare overskrift**: `fetch_ir._scrape_listing()`
fanger kun overskriftteksten fra lenken, aldri brødtekst — det ga tidligere
kunstig korte kommentarer (én setning) for IR-scrapede saker, selv når den
faktiske pressemeldingen hadde nok stoff til 3–6 setninger. `main.py` henter
derfor nå den fulle artikkelteksten (`fetch_ir.fetch_article_body()`) for
hver kandidat som overlever recency-filtreringen — altså en håndfull
saker per kjøring, ikke hele ~20-overskrifters listen per selskap, så
kostnaden holdes lav. Newsweb-saker har alltid hatt full brødtekst allerede
(via `_fetch_message_body()`); dette tetter det samme hullet for
IR-scrape-kilder. Hvis artikkelhentingen feiler (samme WAF/JS-hindre som
listescrapet kan møte på), faller kommentaren tilbake til én kort setning
fra overskriften alene — modellen får aldri lov til å dikte opp detaljer for
å fylle ut lengden.

## Det denne IKKE dekker (med vilje)

**Bloomberg, Upstream og Petrodata** er abonnementstjenester med kun
nettleser-innlogging (ingen API) — de er ikke med i denne automatiseringen.
Enklest workflow: når du sjekker de sidene selv om morgenen og finner noe
relevant, lim inn overskrift + lenke/tekst til Claude i en chat og be om et
utkast i Early Bird-stil — det krever ikke noe eget verktøy, bare spør.

## Manuell testkjøring lokalt

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
export RESEND_API_KEY=...
export FROM_EMAIL=...
python -m src.main
```

## Tidspunkt

Hver utgave sendes **tre ganger** (lagt til 14. juli 2026):

- **16:00 dagen før** — et tidlig varsel. Kjører søndag–torsdag (dagen før
  hver av mandag–fredag-utgavene; ingen kjøring fredag/lørdag ettersom det
  ikke finnes noen lørdag/søndag-utgave å varsle om).
- **07:32** og **08:02** samme morgen som utgaven er for — de to opprinnelige
  kjøringene.

Alle tre er uavhengige scan-og-send-kjøringer med identisk kode — ingen delt
tilstand eller dedup mellom dem. 16:00-varselet kan derfor avvike fra
morgen-utgaven hvis det kommer nytt stoff i mellomtiden (helt tilsiktet, ikke
en bug).

GitHub Actions cron er alltid UTC og håndterer ikke sommertid automatisk, så
workflow-filen trigger litt oftere enn nødvendig i UTC, og
`src/schedule_guard.py` avgjør basert på faktisk Oslo-lokal tid (og ukedag)
om denne kjøringen faktisk skal gjøre noe (ellers avsluttes den umiddelbart
uten kostnad).

Tidsvinduet for hva som regnes som "nytt" i selve scan-logikken er fast:
siden kl. 08:30 Oslo-tid dagen før (fredag 08:30 på mandager, for å dekke
helgen), ikke en rullerende 24-timers periode fra når jobben tilfeldigvis
kjører. Dette er separat fra spørsmålet om *når på dagen* en kjøring skal
skje, som er det `schedule_guard.py` styrer.

### Backup-trigger (GitHub sin schedule er "best effort")

Oppdaget 10. juli 2026: GitHub Actions' egen `schedule`-trigger er ikke
garantert — GitHub sier selv den er "best effort" og kan bli forsinket eller
i sjeldne tilfeller droppet helt, spesielt ved høy belastning på plattformen.
Begge de planlagte kjøringene den morgenen (05:32 og 06:02 UTC) uteble helt
uten noen synlig feil — ingen kjøring dukket opp i det hele tatt, verken
umiddelbart eller forsinket. Dette er ikke en feil i cron-syntaksen eller
`default_branch`-oppsettet (begge ble verifisert korrekte). Observert igjen
13.–14. juli: GitHubs egen `schedule` kom typisk 2–3 timer for sent hver
dag (kjørte, men langt utenfor `schedule_guard.py`s ±12-minutters vindu).

**Første forsøk (10.–14. juli): Claude Code Remote "Routines" som backup.**
Fire ephemerale AI-økter, tidsforskjøvet ~8 min etter hvert av de 4
UTC-tidspunktene, skulle sjekke om GitHub allerede hadde trigget en
kjøring og ellers selv kalle `workflow_dispatch`. Dette fungerte ikke i
praksis — 0 av 8 forsøk over to påfølgende morgener klarte faktisk å
trigge workflowen, tilsynelatende fordi hver korte økt ga opp så fort den
traff en MCP-tilkobling som viste "still connecting" i stedet for å vente/
prøve på nytt. Rutinene er fjernet 14. juli — en LLM-økt i loopen viste seg
å være for skjør til å være en pålitelig backup for noe tidskritisk.

**Nåværende løsning (fra 14. juli): ren HTTP-ekstern cron, ingen AI-økt i
loopen.** En ekstern tidsstyringstjeneste (f.eks. cron-job.org, som
håndterer sommertid automatisk via IANA-tidssonen `Europe/Oslo`) gjør et
autentisert `POST`-kall direkte mot GitHub sitt REST-API — tre separate
cronjobber, én per tidspunkt (07:32, 08:02, 16:00), alle satt til "every
day"; `schedule_guard.py` no-opper trygt de ukedagene et gitt tidspunkt ikke
skal sende (helg for morgen-slottene, fredag/lørdag for 16:00-slottet), så
det er ikke nødvendig å style dag-i-uken i selve cronjobben:

```
POST https://api.github.com/repos/JonasAulie/Early-Bird/actions/workflows/early-bird.yml/dispatches
Authorization: Bearer <fine-grained PAT, kun "Actions: Read and write" på dette repoet>
Accept: application/vnd.github+json
Content-Type: application/json
X-GitHub-Api-Version: 2022-11-28

{"ref": "main"}
```

`workflow_dispatch` starter kjøringer nær umiddelbart (ingen
`schedule`-kø-forsinkelse), og siden treffet skjer på nøyaktig riktig
Oslo-tidspunkt er `schedule_guard.py`s ±12-minutters toleransevindu rikelig
nok — `force` trenger ikke settes. GitHub sin egen upålitelige `schedule`
i `early-bird.yml` beholdes som et helt kostnadsfritt lengre-skudd (den
no-opper trygt via samme guard om den skulle treffe utenfor vinduet, og
kan i sjeldne tilfeller faktisk treffe i tide). PAT-en og selve
cron-jobb-oppsettet ligger utenfor dette repoet, hos den eksterne
tjenesten — ikke i noen fil her.

> **NB:** frem til 14. juli 2026 var `default_branch` satt til en
> utviklings-branch (`claude/epic-gates-li6qlq`) i stedet for `main`, som
> skapte reell forvirring om hvilken branch som var "sannheten". Ryddet opp
> samme dag: alt historikk samlet i `main`, `main` satt som default branch
> på GitHub, og de gamle `claude/*`-branchene slettet. Denne README-en, i
> likhet med resten av repoet, finnes nå kun på `main`.

## Selskapsuniverset

`config/watchlist.json` er en sammenslåing av SEBs egen Energy-dekningsliste
(fra Early Bird-rapportene, inkl. anbefaling Buy/Hold/Sell per dekket
selskap) og listen "Selskaper til mail alert". Legg til, fjern eller
oppdater `recommendation` der etter behov.
