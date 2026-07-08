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

## Kjente begrensninger

- **Blokkert av bot-beskyttelse (403), uansett riktig URL:** Weatherford,
  Chevron, BP, Ørsted. Disse har WAF/Akamai-beskyttelse som avviser
  automatiserte requests uansett User-Agent — løses ikke uten en ekte
  (headless) nettleser, ikke prioritert nå.
- **URL-er som fortsatt ikke er funnet** (404 selv etter flere forsøk):
  Transocean (deepwater.com), Noble Corporation, Seadrill, Kongsberg
  Maritime (kun konsernnivå funnet, ikke Maritime-spesifikt).
- Noen få selskaper i `config/watchlist.json` mangler fortsatt `ir_url`
  (`null`) — spesielt et par mindre norske Euronext Growth-selskaper.
- `scripts/probe_urls.py`, `scripts/probe_newsweb_playwright.py` og
  `scripts/discover_ir_urls.py` er beholdt som permanente feilsøkingsverktøy
  — legg til nye kandidater der og kjør via en midlertidig
  workflow_dispatch-jobb for å teste fra en runner med ekte nettilgang.

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
