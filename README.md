# Early Bird scanner

Automatisk scanner som henter pressemeldinger/børsmeldinger for et
selskapsunivers (se `config/watchlist.json`), filtrerer for relevans, og
sender et utkast (overskrift + kort kommentar, i stil med SEB Early Bird)
på e-post 4 ganger hver morgen.

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

**Sikkerhetsnotat:** Resend-nøkkelen som ble limt inn i chatten bør
regenereres i Resend-dashbordet før den tas i bruk her, siden den har stått
i klartekst i en samtale.

## Kjente begrensninger (verifisert på ekte GitHub Actions-kjøring)

- **Newsweb (Oslo Børs) er en ren JS-app (React SPA).** Alle URL-varianter
  (base-siden og alle API-gjetninger) returnerer nøyaktig samme tomme HTML-
  skall — en enkel `requests.get()` kan aldri hente ekte data derfra uten at
  noen reverse-engineerer de faktiske XHR-kallene appen gjør (krever en ekte
  nettleser/devtools). `src/fetch_newsweb.py` er derfor for øyeblikket
  virkningsløs, men koden feiler ikke — `src/main.py` bruker nå alltid også
  selskapets egen IR-side som fallback for Newsweb-registrerte selskaper.
- **Blokkert av bot-beskyttelse (403), uansett riktig URL:** Weatherford,
  Chevron, BP, Ørsted. Disse har WAF/Akamai-beskyttelse som avviser
  automatiserte requests uansett User-Agent — løses ikke uten en ekte
  (headless) nettleser, ikke prioritert nå.
- **URL-er som fortsatt ikke er funnet** (404 selv etter forsøk på riktig
  sti): Patterson-UTI, Transocean (deepwater.com), Noble Corporation,
  Seadrill. `ir_url` står som beste gjetning i watchlist.json og bør rettes
  manuelt om noen finner riktig lenke.
- **Fikset og verifisert i denne runden:** Eni, Repsol, SBM Offshore,
  Valaris, Orrön Energy (riktig domene er faktisk orron.com, ikke
  orronenergy.com).
- Noen felt i watchlist (`ir_url: null`) mangler helt — spesielt et par av
  de norske Euronext Growth-selskapene (Noram Drilling, Sea1, Cavendish,
  SED Energy Holdings, Bonheur, Magnora, Cloudberry, IWS).
- `scripts/probe_urls.py` er beholdt som et permanent feilsøkingsverktøy —
  legg til nye kandidat-URL-er der og kjør via en midlertidig
  workflow_dispatch-jobb for å teste fra en runner med ekte nettilgang.

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

Jobben er ment å kjøre kl. 06:32, 07:02, 07:32 og 08:02 norsk tid.
GitHub Actions cron er alltid UTC og håndterer ikke sommertid automatisk,
så workflow-filen trigger litt oftere enn nødvendig i UTC, og
`src/schedule_guard.py` avgjør basert på faktisk Oslo-lokal tid om denne
kjøringen faktisk skal gjøre noe (ellers avsluttes den umiddelbart uten
kostnad).

## Selskapsuniverset

`config/watchlist.json` er en sammenslåing av SEBs egen Energy-dekningsliste
(fra Early Bird-rapportene) og listen "Selskaper til mail alert". Legg til
eller fjern selskaper der etter behov.
