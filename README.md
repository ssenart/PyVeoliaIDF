# PyVeoliaIDF

PyVeoliaIDF is a Python library for reading your water consumption from the Veolia Ile-de-France customer area (L'eau d'Île-de-France / SEDIF).

Their water meters are wireless and transmit the consumption once per day. The consumption is available in the customer area (https://connexion.leaudiledefrance.fr), and PyVeoliaIDF reads it from there and gives it as typed Python objects: daily, weekly and monthly readings, the index of the meter, the estimated cost, and the contracts with their meters.

> **Unofficial.** Veolia offers no public API. PyVeoliaIDF calls the same backend that the customer area web pages call, so a change on their side may break it. See [Limitations](#limitations).

**Contents**
[Installation](#installation) ·
[Quick start](#quick-start) ·
[Concepts](#concepts) ·
[Examples](#examples) ·
[Command line](#command-line) ·
[Configuration](#configuration) ·
[Reference](#reference) ·
[Home Assistant](#home-assistant) ·
[Limitations](#limitations) ·
[Reporting an issue](#reporting-an-issue) ·
[Development](#development) ·
[Contributing](#contributing)

## Installation
PyVeoliaIDF needs Python 3.10 or newer. It makes plain HTTPS calls: no browser and no web driver are needed.

```bash
pip install pyveoliaidf            # a final release
pip install --pre pyveoliaidf      # the latest pre-release (alpha, beta or release candidate)
```

## Quick start
The client is asynchronous. Use it as an async context manager, so that the session ends whatever happens.

```python
import asyncio

from pyveoliaidf import Client


async def main():
    async with Client("you@example.com", "your password") as client:
        history = await client.history(last_n_days=7)

        for reading in history.readings:
            print(reading.day, f"{reading.liters:.0f} L")


asyncio.run(main())
```

Output:

```
2026-10-05 530 L
2026-10-06 374 L
2026-10-07 348 L
...
```

## Concepts
The model follows what the Veolia backend offers.

| Object | What it is |
|---|---|
| `Client` | The entry point. Logs in on its first call and keeps the session. |
| `Contract` | A contract of the account: its number, status, organising authority, end date, the served `site` address, the `balance`, its `meters`, and the `customer` and `payer`. |
| `Meter` | A meter of a contract: its `number` and `point_id`. |
| `ConsumptionHistory` | The readings of one meter over a period, with what the site says about them: the average price of water, the leak-flow threshold, the index readings, and a summary (`minimum`, `maximum`, `average_m3`, `total_m3`, `total_cost_eur`). |
| `Reading` | The consumption of one period (a day, a week or a month) with the index of the meter at its end. |
| `Step` | What one reading covers: `Step.DAY`, `Step.WEEK` (Monday to Sunday) or `Step.MONTH`. |

Three things are worth knowing before you use the readings:

* **Volumes are cubic meters, as `Decimal`**, exactly as the site sends them. `reading.liters` and `reading.cost_eur` are derived. The cost is the volume times the average price of water that the site shows, and it is not contractual.
* **`reading.day` is the day that the website shows.** `reading.time` is the moment of the reading as the site sends it; its time of day varies (usually 21:00, sometimes other hours), so use `day` to place a reading on the calendar. For a week or a month, `day` is the last day of the period.
* **Estimated readings and meter changes.** `reading.estimated` marks a day that the site estimates: its volume is not reconciled with the index yet. `reading.meter_changed` is true where the index goes down, which is a meter replacement.

## Examples
The examples assume that they run inside an open client, as in the quick start:

```python
import asyncio

from pyveoliaidf import Client


async def main():
    async with Client("you@example.com", "your password") as client:
        ...  # the example goes here


asyncio.run(main())
```

### Reading the consumption

**The latest reading**

```python
history = await client.history(last_n_days=3)
latest = history.readings[-1]

print(f"{latest.day}: {latest.liters:.0f} L, the meter shows {latest.index_m3} m3")
```

The site publishes a day after it ends, so the latest reading is yesterday's.

**A range of dates**

```python
from datetime import date

history = await client.history(start=date(2026, 7, 1), end=date(2026, 7, 31))

print(f"July: {history.total_m3:.1f} m3 in {len(history.readings)} days")
```

**A whole year** (the site refuses long daily ranges: the client reads them in windows, and merges them)

```python
history = await client.history(last_n_days=365)

print(f"{len(history.readings)} daily readings, from {history.readings[0].day} to {history.readings[-1].day}")
```

**One reading per week or per month**

```python
from pyveoliaidf import Step

weeks = await client.history(step=Step.WEEK, last_n_days=90)
for week in weeks.readings:
    print(f"week ending {week.day}: {week.volume_m3} m3")

months = await client.history(step=Step.MONTH, last_n_days=400)
for month in months.readings:
    print(f"month ending {month.day}: {month.volume_m3} m3")
```

### Analysing the consumption

**The summary of the website** ("Résumé sur la période")

```python
from datetime import date, timedelta

today = date.today()
history = await client.history(start=today - timedelta(days=89), end=today)

low, high = history.minimum, history.maximum
print(f"minimum: {low.day} {low.volume_m3} m3 = {low.cost_eur:.2f} EUR")
print(f"maximum: {high.day} {high.volume_m3} m3 = {high.cost_eur:.2f} EUR")
print(f"average: {history.average_m3:.3f} m3 per day")
```

**What the water costs**

```python
history = await client.history(last_n_days=30)

print(f"price of water: {history.average_price_eur_m3} EUR per m3")
print(f"the last 30 days cost about {history.total_cost_eur:.2f} EUR")
```

**Totals per month, from the daily readings**

```python
from collections import defaultdict
from decimal import Decimal

history = await client.history(last_n_days=365)

totals = defaultdict(Decimal)
for reading in history.readings:
    totals[(reading.day.year, reading.day.month)] += reading.volume_m3

for (year, month), volume in sorted(totals.items()):
    print(f"{year}-{month:02d}: {volume:.1f} m3")
```

**Which weekday uses the most water**

```python
from collections import defaultdict
from statistics import mean

history = await client.history(last_n_days=180)

by_weekday = defaultdict(list)
for reading in history.readings:
    by_weekday[reading.day.strftime("%A")].append(reading.liters)

for weekday, volumes in sorted(by_weekday.items(), key=lambda item: -mean(item[1])):
    print(f"{weekday:<10} {mean(volumes):6.0f} L on average")
```

**Compare this week with the previous one**

```python
from pyveoliaidf import Step

weeks = (await client.history(step=Step.WEEK, last_n_days=21)).readings
previous, last = weeks[-2], weeks[-1]

change = (last.volume_m3 - previous.volume_m3) / previous.volume_m3 * 100
print(f"{last.volume_m3} m3 against {previous.volume_m3} m3 the week before ({change:+.0f} %)")
```

**The days that the site estimates**

```python
history = await client.history(last_n_days=60)

estimated = [reading.day for reading in history.readings if reading.estimated]
print(f"{len(estimated)} estimated days: {estimated}")
```

### Watching for leaks

**Permanent flow.** The site flags a flow that never stops, which is the sign of a leak. The threshold and the flag are in the history, and each reading carries the measured permanent flow.

```python
history = await client.history(last_n_days=30)

print("leak alert enabled on the site:", history.shows_permanent_flow)
print("threshold:", history.permanent_flow_threshold)

for reading in history.readings:
    if reading.permanent_flow:
        print(f"{reading.day}: permanent flow {reading.permanent_flow}")
```

**An unusually high day**

```python
from statistics import mean, pstdev

history = await client.history(last_n_days=90)
volumes = [float(reading.volume_m3) for reading in history.readings]
limit = mean(volumes) + 3 * pstdev(volumes)

for reading in history.readings:
    if reading.volume_m3 > limit:
        print(f"{reading.day}: {reading.liters:.0f} L, far above the usual {mean(volumes) * 1000:.0f} L")
```

### The meter

**The index of the meter** (the "relevés" of the website)

```python
history = await client.history(last_n_days=10)

for index in history.meter_readings:
    print(index.time, index.index_m3, "m3")
```

**A meter replacement.** The index of a new meter starts again from a low value. `meter_changed` marks that reading, so that a calculation on the index can skip it.

```python
history = await client.history(last_n_days=365)

for reading in history.readings:
    if reading.meter_changed:
        print(f"{reading.day}: the index went down to {reading.index_m3} m3")

# the consumption between two dates, from the index, without crossing a replacement
readings = [reading for reading in history.readings if not reading.meter_changed]
print("index grew by", readings[-1].index_m3 - readings[0].index_m3, "m3")
```

### Contracts and meters

**List what the account has**

```python
for contract in await client.contracts():
    print(f"contract {contract.number}: {contract.status}, {contract.authority}")
    print(f"  served address: {contract.site.street}, {contract.site.postal_code} {contract.site.city}")
    print(f"  balance: {contract.balance}")
    for meter in contract.meters:
        print(f"  meter {meter.number} (point {meter.point_id})")
```

**Read a given contract or meter.** Without a choice, the first contract and its first meter are read.

```python
contracts = await client.contracts()
contract = contracts[0]
meter = contract.meters[0]

history = await client.history(last_n_days=30, contract_number=contract.number, meter_number=meter.number)
print(history.contract_number, history.meter_number, len(history.readings))
```

**Every meter of the account**

```python
for contract in await client.contracts():
    for meter in contract.meters:
        history = await client.history(last_n_days=30, contract_number=contract.number, meter_number=meter.number)
        print(f"meter {meter.number}: {history.total_m3:.1f} m3 in 30 days")
```

**Set the choice once.** The client can be given its contract number and meter number.

```python no-run
async with Client("you@example.com", "your password", contract_number="9177697", meter_number="I26JB019724") as client:
    history = await client.history(last_n_days=7)
```

The numbers are what identifies a contract and a meter: they are printed on your invoice and on the meter, and they never change. `contract.id` and `meter.meter_token` are opaque tokens that the site makes anew at each call: do not store them, and do not select with them.

### Exporting the data

**A CSV file**

```python
import csv

history = await client.history(last_n_days=365)

with open("consumption.csv", "w", newline="") as file:
    writer = csv.writer(file)
    writer.writerow(["day", "liters", "index_m3", "estimated", "cost_eur"])
    for reading in history.readings:
        writer.writerow([reading.day, f"{reading.liters:.0f}", reading.index_m3, reading.estimated, f"{reading.cost_eur:.2f}"])
```

**JSON.** The models are Pydantic models. In JSON, decimals are text, so that no precision is lost.

```python
history = await client.history(last_n_days=7)

print(history.model_dump_json(indent=2))
data = history.model_dump(mode="json")      # a dict, ready for json.dump
```

**A pandas DataFrame** (pandas is not a dependency of the library)

```python no-run
import pandas as pd

history = await client.history(last_n_days=365)
frame = pd.DataFrame([reading.model_dump() for reading in history.readings]).set_index("day")
frame["volume_m3"] = frame["volume_m3"].astype(float)

print(frame["volume_m3"].resample("MS").sum())
```

### Credentials

**From the environment, or from a `.env` file**

```python
import os

from pyveoliaidf import Client

client = Client(os.environ["VEOLIAIDF_USERNAME"], os.environ["VEOLIAIDF_PASSWORD"])
```

Keep the password out of your code and out of version control. In Home Assistant, use `!secret`.

### Several calls

**One client, many calls.** The client logs in once, and every call reuses the session.

```python
from pyveoliaidf import Step

week = await client.history(last_n_days=7)
month = await client.history(last_n_days=30)
year = await client.history(step=Step.MONTH, last_n_days=400)
```

**At the same time.** One client is safe for concurrent calls.

```python
import asyncio

from pyveoliaidf import Step

days, weeks, months = await asyncio.gather(
    client.history(last_n_days=30),
    client.history(step=Step.WEEK, last_n_days=90),
    client.history(step=Step.MONTH, last_n_days=400),
)
print(len(days.readings), len(weeks.readings), len(months.readings))
```

### When something goes wrong

Every error that the library raises on its own derives from `PyVeoliaIDFError`.

```python
from pyveoliaidf import (
    LoginError,
    PyVeoliaIDFError,
    RateLimitError,
    ServerError,
    UnexpectedResponseError,
    UnknownContractError,
    UnknownMeterError,
)

try:
    history = await client.history(last_n_days=30, meter_number="NOT-MY-METER")
except UnknownMeterError as error:
    print("no such meter:", error.meter_number)
except UnknownContractError as error:
    print("no such contract:", error.contract_number)
except LoginError:
    print("wrong credentials, or the login page has changed")
except RateLimitError:
    print("the site asks to slow down: try again later")
except UnexpectedResponseError as error:
    print("the site has changed, please report it:", error)   # the message names the field
except ServerError as error:
    print("the site failed or is unreachable:", error, error.status_code)
except PyVeoliaIDFError as error:
    print("any other error of the library:", error)
```

| Error | Meaning |
|---|---|
| `LoginError` | The credentials are wrong, or the login page has changed. |
| `SessionExpiredError` | The site no longer accepts the session. The client logs in again by itself once; this is raised if that fails. |
| `RateLimitError` | The site refused the calls (HTTP 429) after the retries. |
| `ServerError` | The site answered with an error, or could not be reached. It has the HTTP `status_code` when there is one. |
| `UnexpectedResponseError` | The site answered, but not in the shape the library knows: it has changed. The message names the field, never its value. |
| `NotLoggedInError` | A call needs a session, and the client has not logged in. |
| `UnknownContractError`, `UnknownMeterError` | The number is not one of the account. |

### Tuning and debugging

**Timeouts, retries and windows**

```python
from pyveoliaidf import Client, ClientConfig

config = ClientConfig(
    connect_timeout=5,       # seconds
    read_timeout=30,
    retry_count=5,           # retries of a failed call, with an exponential backoff
    retry_delay=2,
    max_window_days=60,      # the size of the windows of a long daily range
)

async with Client("you@example.com", "your password", config=config) as client:
    history = await client.history(last_n_days=365)
```

**Logs.** The library logs through `logging` and never logs credentials, tokens or answers. Turn the details on to see the calls and the retries:

```python
import logging

logging.basicConfig(format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logging.getLogger("pyveoliaidf").setLevel(logging.DEBUG)
```

**Your own HTTP session.** By default the client creates its own, which keeps the login cookies and trusts the intermediate certificate that the Veolia site leaves out of its chain. A session that you give must do both, and the client never closes it.

```python
import aiohttp

import pyveoliaidf

connector = aiohttp.TCPConnector(ssl=pyveoliaidf.build_ssl_context())
async with aiohttp.ClientSession(connector=connector, cookie_jar=aiohttp.CookieJar()) as session:
    async with pyveoliaidf.Client("you@example.com", "your password", session=session) as client:
        history = await client.history(last_n_days=7)
```

### Going lower

The library has three layers (see [the architecture](docs/architecture.md)). You can use the lower ones for what the client does not offer.

**The Veolia API** returns the answers of the site validated, in its own names and units:

```python
from datetime import date, timedelta

from pyveoliaidf import AuraClient, Step, VeoliaApiClient

api = VeoliaApiClient(AuraClient("you@example.com", "your password"))
try:
    await api.login()
    contract_id = (await api.list_contract_ids())[0]      # an opaque token, valid for the next calls only
    details = await api.get_contract_details(contract_id)
    answer = await api.get_consumption(contract_id, details.meters[0], Step.DAY, date.today() - timedelta(days=5), date.today())
    print(len(answer.data.records), answer.average_water_price)
finally:
    await api.close()
```

**Any other method of the backend**, through the Salesforce transport (see the architecture notes on how to find its name):

```python no-run
from pyveoliaidf import AuraClient

aura = AuraClient("you@example.com", "your password")
await aura.login()
value = await aura.call_apex("SomeApexClass", "someMethod", {"parameter": "value"}, page_uri="/espace-particuliers/s/")
```

### Testing your own code
`Client` accepts any object that implements the `VeoliaApi` protocol, so your tests need no network:

```python no-run
from pyveoliaidf import Client

client = Client("user", "password", api=MyFakeApi())
```

The fake that the tests of this library use, which behaves like the real site (the extra day, the limit of the daily range), is in `tests/unit/fakes.py`.

### In a script, a notebook or a scheduled job

```python
import asyncio
import os

from pyveoliaidf import Client


async def yesterday_liters() -> int:
    async with Client(os.environ["VEOLIAIDF_USERNAME"], os.environ["VEOLIAIDF_PASSWORD"]) as client:
        reading = (await client.history(last_n_days=3)).readings[-1]
        return int(reading.liters)


print(asyncio.run(yesterday_liters()))
```

In a Jupyter notebook, which already runs an event loop, use `await` directly in a cell instead of `asyncio.run`.

## Command line

```bash
pyveoliaidf -u 'you@example.com' -d 30                              # the last 30 days, one reading per day
pyveoliaidf --step week --start 2026-01-01 --end 2026-06-30         # one reading per week
pyveoliaidf --step month -d 400                                     # one reading per month
pyveoliaidf --contracts                                             # the contracts and their meters
pyveoliaidf --contract <number> --meter <number> -d 7               # a given contract and meter
```

| Option | Meaning |
|---|---|
| `-u`, `--username` | The account. Default: `$VEOLIAIDF_USERNAME`, then a prompt. |
| `-p`, `--password` | The password. It shows in the process list: prefer `$VEOLIAIDF_PASSWORD`, or the prompt. |
| `-d`, `--days` | The days to read, up to the end. Default 365. |
| `--start`, `--end` | The first and the last day (`YYYY-MM-DD`). `--start` wins over `--days`. |
| `--step` | `day` (default), `week` or `month`. |
| `--contract`, `--meter` | The contract number and the meter number. Default: the first ones. |
| `--contracts` | List the contracts and their meters instead of the readings. |
| `-v`, `--verbose` | Log the calls and the retries to the standard error. Use it for a bug report. |
| `--version` | Print the version. |

The output is JSON, so it combines with the usual tools:

```bash
export VEOLIAIDF_USERNAME='you@example.com'
export VEOLIAIDF_PASSWORD='your password'

pyveoliaidf -d 7 | jq -r '.readings[] | [.day, .volume_m3] | @tsv'
pyveoliaidf --contracts | jq -r '.[].meters[].number'
pyveoliaidf -d 30 | jq '[.readings[].volume_m3 | tonumber] | add'
```

The exit code is 0, or 1 with the error on the output.

> `--contracts` prints personal data (names, mail, phone, addresses), as the site returns it. The readings contain none.

## Configuration
`ClientConfig` is an immutable object with the settings of the HTTP side.

| Setting | Default | Meaning |
|---|---|---|
| `base_url` | `https://connexion.leaudiledefrance.fr` | The site. |
| `user_agent` | A Firefox user agent | Sent with every request: the site refuses requests that do not look like a browser. |
| `connect_timeout`, `read_timeout` | 10 s, 60 s | The timeouts of a call. |
| `retry_count` | 3 | The retries of a call that fails on the network or with HTTP 429, 502, 503 or 504. |
| `retry_delay`, `max_retry_delay` | 1 s, 15 s | The delay before a retry, which doubles at each attempt, with some jitter. A `Retry-After` of the site is honored within the maximum. |
| `max_window_days` | 90 | The size of the windows in which a long daily range is read. The site refuses about 100 days or more. |

## Reference

### `Client`

| Member | |
|---|---|
| `Client(username, password, *, contract_number=None, meter_number=None, config=None, session=None, api=None)` | `api` replaces the Veolia API, for tests. |
| `await client.contracts()` | The active contracts, with their meters: `list[Contract]`. |
| `await client.history(*, step=Step.DAY, start=None, end=None, last_n_days=365, contract_number=None, meter_number=None)` | A `ConsumptionHistory`. The range ends at `end` (today by default) and starts at `start`, or `last_n_days` before. |
| `await client.login()`, `logout()`, `close()` | The session. The context manager does `login()` and `close()`. |

### `Reading`

| Field | Type | |
|---|---|---|
| `day` | `date` | The day that the website shows (the last day of a week or a month). |
| `time` | `datetime` | The moment of the reading, as the site sends it. |
| `volume_m3` | `Decimal` | The consumption of the period. |
| `index_m3` | `Decimal` | The index of the meter at its end. |
| `estimated` | `bool` | The site estimates this period. |
| `index_estimated` | `bool` | The index is estimated. |
| `permanent_flow` | `Decimal \| None` | The measured permanent flow. |
| `meter_changed` | `bool` | The index went down: the meter was replaced or reset. |
| `cost_eur` | `Decimal \| None` | `volume_m3` times the average price of water. Not contractual. |
| `liters`, `index_liters` | `Decimal` | The volume and the index in liters (properties). |

### `ConsumptionHistory`

| Field | |
|---|---|
| `contract_number`, `meter_number`, `point_id` | What was read. |
| `step`, `start`, `end` | The step and the range that were asked for. |
| `period_start`, `period_end` | The period that the site says it covered. |
| `readings` | The `Reading`s, oldest first. |
| `meter_readings` | The index of the meter at each reading date (`MeterIndex`). |
| `average_price_eur_m3` | The average price of water. |
| `permanent_flow_threshold`, `shows_permanent_flow` | The leak alert of the site. |
| `can_compare_month` | The site offers a comparison with the previous month. |
| `retrieved_at` | When the library read it. |
| `minimum`, `maximum`, `average_m3`, `total_m3`, `total_cost_eur` | The summary, computed from the readings (properties). |

### `Contract`, `Meter`, `Site`, `Party`

| | Fields |
|---|---|
| `Contract` | `number` (stable) and `id` (an opaque token, new at each call), `status`, `authority`, `end_date`, `site`, `meters`, `customer`, `payer`, `is_individual`, `has_multiple_contracts`, `segment`, `balance` |
| `Meter` | `number` (stable), `point_id`, and the opaque tokens `meter_token` and `point_token` that the site asks for and makes anew at each call |
| `Site` | `street`, `postal_code`, `city` |
| `Party` | `name`, `salutation`, `first_name`, `last_name`, `email`, `mobile_phone`, `billing_street`, `billing_postal_code`, `billing_city`, `vat_liable`, `large_account`, `locked`, and some identifiers |

The models hold personal data (names, mail, phone, addresses) and the opaque meter tokens. They are left out of the `repr` of the models and are never logged, but do not log or serialize a `Contract` where it could leak. A `ConsumptionHistory` holds none of it.

### What the site gives and does not give

| | |
|---|---|
| Steps | Day, week, month. There is no hourly or yearly step. |
| Daily range | The site refuses about 100 days or more at once. The client windows it. |
| Weekly reading | Dated its Sunday. Its volume is the index difference since the previous week, which is the sum of its seven days unless some are estimated. |
| Estimated day | Its volume does not match the index difference until the site reconciles it. |
| Not offered by the library yet | The billed consumption, the consumption alerts, the forecast of the next invoice, and the comparison with the previous year. The site shows them, but their backend methods are not captured yet. |

## Home Assistant
The custom component [home-assistant-veoliaidf](https://github.com/ssenart/home-assistant-veoliaidf) uses this library. It creates sensors for the yesterday consumption, the period boundaries and the total index of the meter, which can be used in the Energy dashboard.

Home Assistant's shared HTTP session keeps no cookies and does not trust the intermediate certificate of the Veolia site, so the component lets the library create its own session.

## Limitations
PyVeoliaIDF relies on how the Veolia customer area is built. It calls the backend methods of the pages, and any change there may break this library. The library validates every answer and raises an `UnexpectedResponseError` that names what changed, rather than returning wrong data.

The live tests (see below) are the early warning: run them regularly, or on a schedule. If it stops working, see [Reporting an issue](#reporting-an-issue).

## Reporting an issue
Something does not work? Please open an issue at https://github.com/ssenart/PyVeoliaIDF/issues (the form asks for what follows). A good report is mostly a matter of a few facts.

### First, check these
1. **Does the website work?** Log in at https://connexion.leaudiledefrance.fr and open your consumption history. If the site is down, or your login fails there too, it is not the library.
2. **Are you up to date?** Run `pip install --upgrade --pre pyveoliaidf`: the site changes, and the fix may be released already. See the [changelog](CHANGELOG.md).
3. **Is it the credentials?** A `LoginError` means that the login or the password was refused, or that the login page changed. Try them on the website.
4. **Is it a known limit?** See [What the site gives and does not give](#what-the-site-gives-and-does-not-give) and [Limitations](#limitations).

### What to include
| | |
|---|---|
| **What happened, and what you expected** | One or two sentences. Did it ever work, and since when did it stop? |
| **How to reproduce it** | The command line, or the smallest code that shows the problem, with your credentials removed. |
| **The complete error** | The whole message and the traceback, not only the last line. An `UnexpectedResponseError` names the fields that the site changed: that line is the most useful one. |
| **The debug log** | See below. |
| **The versions** | `pyveoliaidf --version`, the Python version, and your operating system. |
| **How it is installed** | `pip` in a virtual environment, Docker, Home Assistant OS or Container, HACS... |
| **The shape of your account** | For instance "1 contract, 1 meter" or "2 contracts". Only the shape, never the numbers. |
| **How often** | Always, sometimes, or once; and the date and time of the last failure. |
| **What you already tried** | A newer version, another network, the website in a browser. |

### Collect the debug log
The library logs through `logging`. At the `DEBUG` level it logs each call (method, path, status, duration) and each retry. It never logs credentials, tokens, cookies or the answers of the site.

From the command line, add `-v`: the log goes to the standard error, and the result to the standard output.

```bash
pyveoliaidf -v -d 7 2> pyveoliaidf.log
```

From your code:

```python
import logging

logging.basicConfig(format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logging.getLogger("pyveoliaidf").setLevel(logging.DEBUG)
```

With the Home Assistant component, add this to `configuration.yaml`, restart, reproduce the problem, and take the lines from Settings, System, Logs (or from `home-assistant.log`):

```yaml
logger:
  default: warning
  logs:
    custom_components.veoliaidf: debug
    pyveoliaidf: debug
```

### Check what you share
Read the log and the code before you post them, and replace with `XXX`:

* **Never share:** your password, tokens, cookies, the `aura.token`, session or `sid` values.
* **Remove or hide:** your login (mail), contract numbers, meter numbers, names, addresses, phone numbers, and the identifiers that look like long random text.
* **Safe to share:** the versions, the error messages, the names of the fields in an `UnexpectedResponseError`, the dates and the status codes of the log, and consumption values if you wish.

If you cannot share something safely, say what it is rather than leaving it out silently.

### If the site has changed
When a field, a method or a step changed, the maintainer needs to see what the site now sends. If you are comfortable with it, open the browser developer tools (Network tab, filter on `aura`), reload the history page, and describe what differs. Share only the `classname` and `method` and the *names* of the fields, never the cookies or the values: see [Adding something the site offers](#adding-something-the-site-offers) for what is safe.

### Security problems
If you found a way to read someone else's data, or a leak of credentials, do not open a public issue: contact the maintainer privately, through the address on the [PyPI page](https://pypi.org/project/pyveoliaidf/) or [GitHub profile](https://github.com/ssenart).

# Development

## Prerequisites
* [git](https://git-scm.com/)
* [uv](https://docs.astral.sh/uv/getting-started/installation/), which manages Python, the virtual environment and the dependencies. You do not need to install Python 3.10 to 3.14 yourself: uv downloads what the project asks for.
* An editor with Python support. For VS Code, see [VS Code](#vs-code) to set up the Testing panel.
* To run the live tests only: a Veolia Ile-de-France account.

## Checkout and set up

```bash
git clone https://github.com/ssenart/PyVeoliaIDF.git
cd PyVeoliaIDF
git switch develop              # the integration branch; see "Branches and versions"
uv sync                         # creates .venv and installs the locked dependencies and the package, editable
```

`uv sync` reads `pyproject.toml` and `uv.lock`, so everybody gets the same versions. Prefix a command with `uv run` to run it in that environment, or activate it (`source .venv/bin/activate`).

## Project layout

```
src/pyveoliaidf/
  aura.py            the generic Salesforce Aura transport: bootstrap, login, Apex calls
  resilience.py      the retry policy
  tls.py, certs/     the TLS context, with the intermediate certificate that the site leaves out
  config.py          ClientConfig
  api_client.py      the Veolia API: the Apex methods, their parameters
  veolia_models.py   the raw answers, validated (the site's names and units)
  convert.py         raw answers -> public model, windowing
  model.py           the public model: Contract, Reading, ConsumptionHistory, Step
  client.py          the public Client
  errors.py          the errors
  __main__.py        the command line
tests/
  unit/              offline tests, with a fake site and fakes of the layers
  integration/       live tests against the real site (opt-in)
docs/architecture.md the layers, the Aura protocol, what is verified against the real site
.github/workflows/   ci.yaml, create-release.yaml; dependabot.yml
```

The layers and what to edit when the site changes are in [docs/architecture.md](docs/architecture.md).

## The daily workflow

| Task | Command |
|---|---|
| Install or update the environment | `uv sync` |
| Unit tests (offline) with the coverage gate | `uv run pytest --cov` |
| Unit tests, fast | `uv run pytest` |
| One test, or a keyword | `uv run pytest tests/unit/test_client.py::TestWindowing -k year` |
| Live tests (need credentials) | `uv run pytest -m integration -rs` |
| Format | `uv run ruff format .` |
| Lint (and fix what can be) | `uv run ruff check --fix .` |
| Types | `uv run mypy .` |
| **Everything CI checks** | `uv run ruff format --check . && uv run ruff check . && uv run mypy . && uv run pytest --cov` |
| Build the sdist and the wheel | `uv build` |
| Run the command line from the sources | `uv run pyveoliaidf --help` |
| Update the locked dependencies | `uv lock --upgrade && uv sync` |
| Add a dependency | `uv add <package>` (runtime) or `uv add --dev <package>` |

Run the "everything CI checks" line before you push. It takes a few seconds.

## Tests
There are two suites, kept strictly apart.

### Unit tests: `tests/unit`
They run offline by default, in about two seconds, and need no credentials.

* The Salesforce transport runs for real against a **fake site** on the loopback (`tests/unit/fake_site.py`): an aiohttp server that scripts what the Aura endpoint answers, so the cookies, the redirects and the forms are exercised.
* The upper layers run against **fakes of the layer below** (`tests/unit/fakes.py`). `FakeApi` behaves like the real site: it answers a daily range with the day that precedes the start, and it refuses a daily range of more than about 100 days.
* A guard (`tests/unit/conftest.py`) fails any test that reaches beyond the loopback, and removes the credentials of the live tests from the environment.
* `hypothesis` property tests cover the parsers and the windowing.
* The coverage gate is **95%** (with branches), enforced with `--cov`. Today it is above 99%: keep it there. A new line needs a test.

### Live tests: `tests/integration`
They log in to the real site, **read only**, and are deselected by default (`pytest.ini` has `addopts = -m "not integration"`).

```bash
cp .env.example .env            # then fill in your credentials; .env is ignored by git
uv run pytest -m integration -rs
```

* The credentials come from `VEOLIAIDF_USERNAME` and `VEOLIAIDF_PASSWORD`, in the environment or in `.env`. Without them the live tests **skip**, with the reason, and never fail.
* They check what the unit tests cannot: that the site still answers as the library expects (the shapes, the three steps, the daily range limit, the windowing, a weekly reading against its days), and the whole path through the command line.
* They are polite: one login per module, and they only read. A run takes about a minute, mostly the one-year histories.
* A live test that fails while the unit tests pass means **the site changed**: see [When the site changes](#when-the-site-changes).

### VS Code
`.vscode/` is not committed (it is git-ignored), so create `.vscode/settings.json` once to let the Testing panel discover the tests:

```json
{
    "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
    "python.testing.pytestEnabled": true,
    "python.testing.unittestEnabled": false,
    "python.testing.pytestArgs": ["tests"],
    "python.testing.autoTestDiscoverOnSaveEnabled": true,
    "python.envFile": "${workspaceFolder}/.env"
}
```

Then run **Python: Select Interpreter** (choose `.venv/bin/python`), reload the window, and refresh the Testing panel. With these settings only the unit tests are listed, because `pytest.ini` deselects the live ones. To list the live tests too, add `"-o", "addopts="` to `pytestArgs`; **Run All** would then run them, with the credentials of `.env`.

## Code style and conventions
* **ruff** formats (`ruff format`) and lints (`ruff check`: pycodestyle, pyflakes, isort, naming, bugbear, pyupgrade, unused arguments, simplifications, blind exceptions). Line length 120.
* **mypy `--strict`** on the sources and on the tests.
* Public types are Pydantic models; volumes are `Decimal` cubic meters; no floats for money or volume.
* **Never log or put in an exception message** a password, a token, an Aura payload, or personal data. Errors name the field, not its value. Tests check the logs.
* Comments explain *why*, not what; docstrings are short.
* Every change updates `CHANGELOG.md` under `[Unreleased]` ([Keep a Changelog](https://keepachangelog.com/en/1.0.0/)), and the README or the architecture notes when behaviour or design changes.

## Adding something the site offers
A new backend method goes through every layer, bottom up:

1. **Find the call.** In the website, open the browser developer tools, Network tab, filter on `aura`, and use the feature. The `message` form field of the POST holds `classname` and `method`, and the `params`. Copy only those: the cookies and the `aura.token` are secrets, never put them in the repository or in an issue.
2. **`veolia_models.py`:** a model of the answer, with the site's names as aliases. Leave personal fields out of the `repr`.
3. **`api_client.py`:** a method that sends the parameters and validates the answer (`validate(...)`), and add it to the `VeoliaApi` protocol.
4. **`model.py` and `convert.py`:** the public model and the conversion.
5. **`client.py`:** the method that users call.
6. **Tests:** unit tests with a fixture of the answer (scrub every personal value), the fakes updated in `tests/unit/fakes.py`, and a live test that checks the real shape.
7. **Docs:** the README (an example, the reference), `docs/architecture.md` (the observed behaviour), and the changelog.

## When the site changes
The library is meant to fail loudly and precisely.

1. A live test, or a user, reports an `UnexpectedResponseError`. Its message names the fields that changed.
2. Run `uv run pytest -m integration -rs` to see what still works.
3. Capture the call as in "Adding something the site offers", compare it with the models, and fix the layer that owns the change (`aura.py` for the framework build, the login or the token; `api_client.py` and `veolia_models.py` for a method, a parameter or a field).
4. Add a unit test that reproduces it, run everything, and release a patch version.

## Continuous integration
`.github/workflows/ci.yaml` runs on every push to `master`, `develop`, `release/*` and `feature/*`, on pull requests, and by hand (`workflow_dispatch`, with inputs to skip the lint or the tests).

| Job | What it does |
|---|---|
| **Lint** (Python 3.14) | `ruff format --check`, `ruff check`, `mypy .` |
| **Test**, a matrix on Python **3.10, 3.11, 3.12, 3.13, 3.14** | `pytest tests --cov` (the unit tests, with the 95% gate) |
| **Live tests**, on the default Python only | `pytest tests/integration -m integration -rs`, once per run to keep the logins on the site few. They skip, with the reason, when the secrets are not set (forks, for instance). |

Set the repository secrets `VEOLIAIDF_USERNAME` and `VEOLIAIDF_PASSWORD` (Settings, Secrets and variables, Actions) to run the live tests in CI. A red live test on every branch means that the site changed.

`.github/dependabot.yml` proposes weekly updates of the Python dependencies and of the GitHub Actions.

## Branches and versions

| Branch | Used for | Versions that can be released from it |
|---|---|---|
| `feature/*` | One change | Any, published to **TestPyPI** only |
| `develop` | Integration | Alpha: `X.Y.ZaN` |
| `release/X.Y.Z` | Stabilizing a release | Beta `X.Y.ZbN` or release candidate `X.Y.ZrcN`, with the same `X.Y.Z` as the branch |
| `master` | What is released | Final: `X.Y.Z` |

Versions follow [PEP 440](https://peps.python.org/pep-0440/) and [semantic versioning](https://semver.org/): a breaking change of the public API bumps the minor version while the major is 0, and the major afterwards. The version lives in `pyproject.toml` only; `pyveoliaidf.__version__` is read from the installed metadata. **Do not edit the version by hand:** the release workflow does.

A typical flow:

```
feature/x ──PR──► develop ──(alphas 0.5.1a1, a2, ...)──► release/0.5.1 ──(0.5.1b1, 0.5.1rc1)──► master ──(0.5.1)
```

After a release from `master`, merge `master` back into `develop`.

## Creating a release
Releases are created by the **Create Release** workflow (`.github/workflows/create-release.yaml`), run by hand. It does everything, in an order that keeps the irreversible steps last.

### One-time setup
* GitHub environments **`pypi`** and **`testpypi`** (Settings, Environments). Add required reviewers to `pypi` if you want a manual approval before a publication.
* A **trusted publisher** on [PyPI](https://pypi.org/manage/account/publishing/) and on [TestPyPI](https://test.pypi.org/manage/account/publishing/) for the project: owner `ssenart`, repository `PyVeoliaIDF`, workflow `create-release.yaml`, environment `pypi` (respectively `testpypi`). There is no API token to store.
* The repository secrets `VEOLIAIDF_USERNAME` and `VEOLIAIDF_PASSWORD`, for the live tests of CI.

### Steps
1. **Get the branch ready.** Everything is merged into the branch you release from (`develop` for an alpha, `release/X.Y.Z` for a beta or a release candidate, `master` for a final version). `CHANGELOG.md` has the changes under `## [Unreleased]`: the workflow refuses an empty section.
2. **Check that CI is green on the last commit.** The workflow checks it too, and waits for a running CI for up to 30 minutes.
3. **Try it with a dry run.** On GitHub, Actions, **Create Release**, Run workflow: pick the branch, enter the version (for instance `0.5.1a1`), keep *Create the GitHub release as a draft* and tick **Dry run**. It validates, bumps, builds and reports, but pushes, publishes and releases nothing. Read the summary.
4. **Run it for real**, the same without the dry run.
5. **Publish the draft.** The workflow creates the GitHub release as a draft, with the changelog section as its notes, and marks pre-releases. Check the notes, then publish it.
6. **Afterwards.** Merge `master` back into `develop` after a final release. Update the consumers: in `home-assistant-veoliaidf`, require the new version in `custom_components/veoliaidf/manifest.json` and `pyproject.toml`.

### What the workflow does
1. **Preflight**, before anything is changed:
   * the version is valid PEP 440, canonical (`0.5.1a1`, not `0.5.1-alpha1`), and not a dev or local version;
   * the version kind matches the branch (the table above), and a `release/X.Y.Z` branch matches the version's base;
   * the tag does not exist, and the version is greater than every existing tag;
   * `[Unreleased]` in the changelog is not empty;
   * CI passed on this exact commit.
2. **Release**, in this order:
   * `uv version` bumps `pyproject.toml` and `uv.lock`;
   * the changelog is finalized: `[Unreleased]` becomes `[X.Y.Z] - date`, a new empty `[Unreleased]` is put on top, and the compare links are regenerated; the released section is kept as the release notes;
   * `uv build` makes the sdist and the wheel;
   * the package is published to **PyPI** (from `master`, `develop` and `release/*`) or **TestPyPI** (from `feature/*`), through trusted publishing;
   * the bump commit (`Bump version to X.Y.Z`) is made, tagged `X.Y.Z`, and pushed together with the tag, atomically;
   * the GitHub release is created.

   Everything irreversible (the publication) happens before the commit and the tag are pushed, so a failed publication leaves the repository untouched.
3. A summary of the run is written to the job summary, even on failure.

### If a release fails
* **Before the publication:** nothing has changed. Fix the cause and run it again.
* **After the publication, before the push** (a rare failure of the push): the package is on PyPI and cannot be replaced. Bump to the next version, and run the workflow again.
* A version that is on PyPI can be *yanked* (hidden from the resolvers), never deleted and reused.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `uv sync` fails on a missing Python | Run `uv python install 3.14`, or let uv do it: it downloads the version asked by `requires-python`. |
| The live tests are all skipped | The credentials are not set: see `.env.example`. `-rs` prints the reason. |
| A live test fails, unit tests pass | The site changed: see [When the site changes](#when-the-site-changes). |
| A unit test reports "tried to reach ... the unit tests run offline" | The test or the code opens a real connection: use the fake site or a fake layer. |
| `mypy` complains about a test | The tests are typed too (`mypy --strict`): annotate the functions. |
| `uv lock` wants to change the lockfile in CI (`--locked`) | You changed `pyproject.toml` without running `uv lock`: run it and commit `uv.lock`. |
| VS Code shows "Missing Module" in the Testing panel | The panel uses another interpreter: select `.venv/bin/python`, reload the window, and refresh the tests. |
| `ssl.SSLCertVerificationError` to the Veolia site with your own HTTP client | The site does not send its intermediate certificate: use `pyveoliaidf.build_ssl_context()`. |

## Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

Please make sure to update the tests as appropriate: the unit tests must stay offline, and what needs the real site belongs to the integration tests. Run the "everything CI checks" line before you push, and add a line to the changelog.

Never include credentials, tokens, cookies, or personal data from the site in an issue, a pull request, a test fixture or a log.

## License
[MIT](https://choosealicense.com/licenses/mit/)

## Project status
PyVeoliaIDF has been initiated for integration with [Home Assistant](https://www.home-assistant.io/).
