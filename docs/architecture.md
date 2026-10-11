# Architecture

```
 user code / Home Assistant
          │  async API: Client, DailyReading
┌─────────▼──────────┐
│ client.py          │  upper layer: what users see
│ model.py           │  converts raw records → DailyReading (m³ → L, estimated flag, dates)
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
4. **The Veolia methods.** `LTN009_ICL_ContratsGroupements.listCurrentUserActiveContrats` (contract identifiers), `LTN008_ICL_ContratDetails.getContratDetails` (the meter tokens), `LTN015_ICL_ContratConsoHisto.getData` (the history; `TYPE_PAS` is `JOURNEE`, `SEMAINE` or `MOIS`). Volumes and indexes come as cubic meters in text.

The site does not send its intermediate certificate, so `tls.py` adds the Gandi one that `certs/` bundles.

## What has been verified against the real site
Verified live (the integration tests exercise them): the bootstrap context, the login and its redirect, the CSRF cookie, the three Apex methods with the `JOURNEE` step, and the answers' shapes.

Assumed, not observed: the `SEMAINE` and `MOIS` steps (the library only requests `JOURNEE`), the `invalidSession` and `clientOutOfSync` events, and HTTP 401/403 as the end of a session. They are Salesforce conventions, covered by the offline tests against a fake site, but the real site has never been seen to send them.

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
