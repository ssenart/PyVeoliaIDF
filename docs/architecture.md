# Architecture

```
 user code / Home Assistant
          │  async API: Client, Contract, ConsumptionHistory
┌─────────▼──────────┐
│ client.py          │  upper layer: contracts and histories, windowing
│ model.py           │  what users get: Contract, Reading, ConsumptionHistory
│ convert.py         │  converts the raw records to that model
└─────────┬──────────┘
          │  VeoliaApi (Protocol)
┌─────────▼──────────┐
│ api_client.py      │  lower layer: the Veolia backend methods and their parameters
│ veolia_models.py       │  validated raw models (the site's names and units)
└─────────┬──────────┘
          │  AuraTransport (Protocol)
┌─────────▼──────────┐
│ aura.py            │  Salesforce Aura transport: bootstrap, login, Apex calls
│ resilience.py      │  retry policy;  tls.py: certificates;  config.py: settings
└─────────┬──────────┘
          ▼  HTTPS  connexion.leaudiledefrance.fr/s/sfsites/aura
```

Each layer depends on the one below through a `Protocol`, so the tests give it a fake (`tests/unit/fakes.py`).

## The Aura protocol, as the library uses it
The customer area is a Salesforce Experience site. Its pages do not call a REST API: they post *actions* to one endpoint, and the actions run Apex methods.

1. **Bootstrap.** Every page carries a JSON context (`mode`, `app`, `fwuid`, `loaded`) in the URLs of its scripts (`/s/sfsites/l/{url-encoded JSON}/app.js`). Every call sends it back as `aura.context`. `fwuid` names the framework build: when the server deploys, it changes, and the server tells so with a `clientOutOfSync` event and a new context in its answer.
2. **Login.** The action `apex://LightningLoginFormController/ACTION$login` takes the credentials. An accepted login answers with a `clientRedirect` event to `frontdoor.jsp`, which sets the session cookies; a refused one answers with a message. The CSRF token (`aura.token`) is the value of the cookie whose name holds `ERIC`.
3. **Apex calls.** `aura://ApexActionController/ACTION$execute` runs `classname.method(params)`. The answer is wrapped in `returnValue`, and `state` says `SUCCESS` or `ERROR`. An `invalidSession` event (or HTTP 401/403) means the session has ended.
4. **The Veolia methods.** `LTN009_ICL_ContratsGroupements.listCurrentUserActiveContrats` (contract identifiers), `LTN008_ICL_ContratDetails.getContratDetails` (the contract, its meters and tokens, the customer and the payer), `LTN015_ICL_ContratConsoHisto.getData` (the history). Volumes and indexes come as cubic meters in text.

## The consumption method, as observed
Verified by live calls and by the integration tests:

* **Identifiers are not stable.** The contract identifiers of the list, the `Id` of the details and the meter tokens (`ELEMA`, `ELEMB`) are encrypted by the site and differ at every call, even within a session. Only the contract number (`Name`) and the meter number (`NUM_COMPTEUR`) are stable, so the client selects by number: it reads the details of each contract until one has the number, then uses the identifier and the tokens of that same call.
* **Steps.** `TYPE_PAS` is `JOURNEE`, `SEMAINE` or `MOIS`. `HEURE`, `HORAIRE`, `ANNEE` and `TRIMESTRE` fail with a server error.
* **Daily range limit.** A daily range of about 100 days or more fails with *Attempt to de-reference a null object*, wherever it sits. Weekly and monthly ranges are accepted over a longer time (monthly: 1000 days). `Client.history()` cuts a long daily range in windows of 90 days.
* **The extra day.** A daily answer starts one day before the requested start (the site converts the start date to UTC). The library clips the days to the range.
* **What a record is.** The date of `DATE_INDEX` is the day that the website shows: the minimum and the maximum of a period match the website's figures to the cent when the volume is multiplied by `prixMoyenEau`. The time of day varies (21:00 usually, but also 07:00, 12:00, 18:00), so it is not a clock time. A weekly record is dated its Sunday, and its volume is the index difference since the previous week, which is the sum of the seven days unless some are estimated.
* **Estimated days.** An estimated day (`FLAG_ESTIMATION`) has a volume that does not match the index difference.
* **Meter replacement.** The index goes down (for instance from 1925 m³ to 30 m³), and a monthly record can have an index of 0.
* **The summary.** The answer carries the maximum, its day, the average, the average price of water, the leak-flow threshold, and the readings of the index (`indexMesure`). The summary fields are an empty text when the site did not compute them.

Not captured: the methods behind "Consommation facturée", "Alertes de consommation", the forecast and the comparison with the previous year. Their Apex methods are not in the page bundles (the components load lazily), so they need a capture of the browser's calls.

The site does not send its intermediate certificate, so `tls.py` adds the Gandi one that `certs/` bundles.

## What has been verified against the real site
Verified live (the integration tests exercise them): the bootstrap context, the login and its redirect, the CSRF cookie, the three Apex methods, the three steps, the daily range limit, the windowing, and the semantics above.

Assumed, not observed: the `invalidSession` and `clientOutOfSync` events, and HTTP 401/403 as the end of a session. They are Salesforce conventions, covered by the offline tests against a fake site, but the real site has never been seen to send them. Accounts with several contracts or meters are covered by the offline tests only.

## Concurrency
One `AuraClient` serves concurrent calls. A lock serializes the logins, and a login counter makes the calls that see the session end at the same time log in once between them.

## Where a change goes
| The site changed… | Edit |
|---|---|
| framework build, login, token handling | `src/pyveoliaidf/aura.py` |
| a method name, a parameter, a field | `api_client.py`, `veolia_models.py` |
| what users get | `model.py`, `client.py` |

## Tests
* `tests/unit` — offline. The transport runs for real against a fake site on the loopback (`fake_site.py`); a guard fails any test that reaches further, and the credentials of the live tests are removed from the environment. Includes property-based tests (`hypothesis`). Coverage gate: 95% (`pytest --cov`).
* `tests/integration` — `pytest -m integration`, live and read-only; needs `VEOLIAIDF_USERNAME` / `VEOLIAIDF_PASSWORD` (environment or `.env`). Skipped without them.
