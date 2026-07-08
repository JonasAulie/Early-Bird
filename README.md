# Early Bird scanner

Automatisk scanner som henter pressemeldinger/børsmeldinger for et
selskapsunivers (se `config/watchlist.json`), filtrerer for relevans, og
sender et utkast (overskrift + kommentar, i SEBs Early Bird-stil) på e-post
3 ganger hver morgen.

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
til kontoeierens egen adresse. **Ikke** verifiser `seb.no` i Resend — det er
SEB sitt bedriftsdomene og krever DNS-endringer bare IT-avdelingen bør gjøre.
Vil du legge til `jonas.aulie@seb.no` igjen: verifiser et domene du faktisk
eier selv i Resend, og legg adressen til i `DEFAULT_RECIPIENTS`.

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

## Dedup: hvorfor en LLM-feilvurdering ikke lenger begraver en sak permanent

`src/main.py` markerer hentede saker som «sett» i `state/seen.json` slik at
de ikke evalueres på nytt (og koster tokens) hver kjøring. For IR-scraping
(høyt volum, mest støy) skjer dette uansett hva modellen konkluderer. For
**Newsweb**-saker (sjeldne, offisielle børsmeldinger) markeres en sak derimot
kun som «sett» hvis den faktisk ble beholdt av relevansfilteret (og dermed
sendt) — ikke bare fordi den ble hentet. Årsak: en reell børsmelding fra TGS
(salg av virksomhet til Enverus) ble hentet korrekt og besto recency-sjekken,
men relevansfilteret (Claude) feilvurderte den som irrelevant i én kjøring —
og den gamle koden markerte den som «sett» uansett, så den forsvant permanent
og kunne aldri dukke opp igjen i noen senere kjøring. Nå får en Newsweb-sak
en ny sjanse på neste kjøring helt til den enten blir sendt eller faller ut
av tidsvinduet naturlig (1–3 dager).

Hvis noe fortsatt mangler: `src/main.py` logger nå hver kandidat som ble
hentet (selskap, dato, tittel) og alt relevansfilteret droppet — les
run-loggen på GitHub Actions for å se nøyaktig hva som skjedde med en
konkret sak, i stedet for å måtte skrive et eget probe-script.

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

## Kjente begrensninger

- **JS-rendrede IR-sider gir null treff, uansett riktig URL:** en vanlig
  `requests.get()` ser bare skallet en SPA sender ut før JavaScript kjører.
  Bekreftet for Baker Hughes (`bakerhughes.com/company/news` gir 848 bytes
  tomt skall, ingen overskrifter) via `scripts/probe_bakerhughes.py` — samme
  klasse problem som Newsweb hadde, men uten en tilsvarende offentlig
  JSON-API å reverse-engineere. Rammer trolig flere av de store
  utenlandske selskapene (mange viser `0/15 med dato` i loggen — noen av de
  er nok tomme skall som dette, andre er ekte server-rendrede sider som bare
  mangler en datostreng nær overskriften). Løsning krever en ekte
  (headless) nettleser i produksjonsscanneren, ikke bare i et probe-script —
  ikke gjort ennå, si ifra om det skal prioriteres.
- **Kan fortsatt bli blokkert av bot-beskyttelse (403):** Weatherford,
  Chevron, BP, Ørsted har WAF/Akamai-beskyttelse som kan avvise automatiserte
  requests uansett User-Agent. De har nå fått de oppgitte IR-URL-ene (juli
  2026); om en runner-kjøring viser 403 for disse, krever det en ekte
  (headless) nettleser å komme forbi — ikke prioritert nå.
- Transocean, Noble, Seadrill og Kongsberg Maritime har nå fått spesifikke
  IR-URL-er (juli 2026); disse verifiseres på neste live-kjøring.
- Noen få selskaper i `config/watchlist.json` mangler fortsatt `ir_url`
  (`null`) — spesielt et par mindre norske Euronext Growth-selskaper.
- `scripts/probe_urls.py`, `scripts/probe_newsweb_playwright.py`,
  `scripts/probe_bakerhughes.py` og `scripts/discover_ir_urls.py` er beholdt
  som permanente feilsøkingsverktøy — legg til nye kandidater der og kjør via
  en midlertidig workflow_dispatch-jobb for å teste fra en runner med ekte
  nettilgang.

## Drafting-stil

`src/draft.py` sitt system-prompt inneholder ekte eksempler fra tidligere
Early Bird-utgaver (format, informasjonstetthet, når man avslutter med en
kort vurdering som "Neutral for Equinor." eller "Share price positive.").
Oppdater few-shot-eksemplene der om stilen bør justeres videre.

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

Jobben er ment å kjøre kl. 07:02, 07:32 og 08:02 norsk tid (siste versjon
med 06:32 fjernet). GitHub Actions cron er alltid UTC og håndterer ikke
sommertid automatisk, så workflow-filen trigger litt oftere enn nødvendig i
UTC, og `src/schedule_guard.py` avgjør basert på faktisk Oslo-lokal tid om
denne kjøringen faktisk skal gjøre noe (ellers avsluttes den umiddelbart
uten kostnad).

Tidsvinduet for hva som regnes som "nytt" er fast: siden kl. 08:30 Oslo-tid
dagen før (fredag 08:30 på mandager, for å dekke helgen), ikke en rullerende
24-timers periode fra når jobben tilfeldigvis kjører.

## Selskapsuniverset

`config/watchlist.json` er en sammenslåing av SEBs egen Energy-dekningsliste
(fra Early Bird-rapportene, inkl. anbefaling Buy/Hold/Sell per dekket
selskap) og listen "Selskaper til mail alert". Legg til, fjern eller
oppdater `recommendation` der etter behov.
