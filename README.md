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
| `FROM_EMAIL` | En adresse på et domene du har **verifisert** i Resend (resend.com/domains). Uten verifisert domene kan Resend kun sende til kontoeierens egen adresse, ikke begge mottakerne. |

Mottakere (`jonasaulie@gmail.com`, `jonas.aulie@seb.no`) er hardkodet i
`src/emailer.py` — endre `DEFAULT_RECIPIENTS` der om det skal endres.

**Sikkerhetsnotat:** Resend-nøkkelen som ble limt inn i chatten bør
regenereres i Resend-dashbordet før den tas i bruk her, siden den har stått
i klartekst i en samtale.

## ⚠️ Ting som IKKE er verifisert ennå (viktig)

Dette ble bygget i et miljø uten internettilgang, så følgende er
beste-gjetning som **må testes** på en ekte kjøring (bruk "Run workflow"-
knappen i GitHub Actions-fanen for en manuell test):

1. **Newsweb-endepunktet** i `src/fetch_newsweb.py` (`CANDIDATE_ENDPOINTS`)
   er en beste gjetning på URL-mønster. Kjør `debug_probe()`-funksjonen der,
   eller åpne newsweb.oslobors.no i en nettleser med devtools/Network åpent,
   filtrer på et selskap, og kopiér den faktiske forespørsels-URL-en og
   svar-formatet inn i `_normalize()`.
2. **IR-side-URLene** i `config/watchlist.json` er beste gjetning på hvor
   hvert selskaps pressemeldinger ligger — noen er sikkert feil eller
   utdaterte, og noen sider er trolig JS-rendret (gir da tomt resultat fra
   `requests.get`, siden vi ikke kjører en headless browser).
3. Noen felt i watchlist (`ir_url: null`) mangler helt — spesielt et par av
   de norske Euronext Growth-selskapene (Noram Drilling, Sea1, Cavendish,
   SED Energy Holdings, Bonheur, Magnora, Cloudberry, IWS).

Første ordentlige kjøring bør behandles som en debug-runde, ikke en
produksjonskjøring — sjekk logg-outputen i Actions-fanen for `WARNING`-
linjer, som forteller nøyaktig hvilke selskaper som ikke ga treff.

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
