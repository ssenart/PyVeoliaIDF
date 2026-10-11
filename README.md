# PyVeoliaIDF
PyVeoliaIDF is a Python library for getting the water consumption from the Veolia Ile-de-France customer area (L'eau d'Île-de-France / SEDIF).

Their water meters are wireless and transmit the consumption once per day. The consumption is available in the customer area (https://connexion.leaudiledefrance.fr), and PyVeoliaIDF reads it from there and gives it as Python objects.

> **Unofficial.** Veolia offers no public API. PyVeoliaIDF calls the same backend that the customer area web pages call, so a change on their side may break it. See [Limitation](#limitation).

## Installation
PyVeoliaIDF needs Python 3.10 or newer. It makes plain HTTPS calls: no browser and no web driver are needed.

```bash
pip install pyveoliaidf
```

### Development environment
The project is managed with [uv](https://docs.astral.sh/uv/).

```bash
cd /path/to/pyveoliaidf/
uv sync
uv run pytest --cov                  # the unit tests: offline, with the 95% coverage gate
uv run pytest -m integration         # the live tests: they need credentials (see below)
uv run ruff check . && uv run mypy .
```

The live tests log in to the real site and only read. Put your credentials in a `.env` file (copy `.env.example` to `.env`, which git ignores) or export `VEOLIAIDF_USERNAME` and `VEOLIAIDF_PASSWORD`. Without them, the live tests are skipped.

## Usage

### Command line

```bash
$ pyveoliaidf -u 'your login' -p 'your password' -d 365
```

### Library
The client is asynchronous.

```python
import asyncio

from pyveoliaidf import Client


async def main():
    async with Client('your login', 'your password', last_n_days=365) as client:
        readings = await client.load_since(30)      # a list of DailyReading, oldest first
        for reading in readings:
            print(reading.time, reading.daily_liter)

        await client.update()                       # the same, as dicts:
        print(client.data())                        # [{"time": ..., "total_liter": ..., ...}, ...]


asyncio.run(main())
```

By default the client creates its own HTTP session, which keeps the login cookies and trusts the intermediate certificate that the Veolia site leaves out of its chain. `Client` also accepts an `aiohttp.ClientSession` (`session=`), which then must do both: build it with `aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=pyveoliaidf.build_ssl_context()))`. Home Assistant's shared session does neither, so let the client create its own. A session that is given is never closed by the client.

### Output

```json
[
  {
    "time": "2026-10-05 21:00:00",
    "total_liter": 143868,
    "daily_liter": 530,
    "type": "Estimé",
    "timestamp": "2026-10-11T12:27:29.330899"
  },
  {
    "time": "2026-10-06 21:00:00",
    "total_liter": 144242,
    "daily_liter": 374,
    "type": "Mesuré",
    "timestamp": "2026-10-11T12:27:29.330899"
  }
]
```

The volumes are liters (integers), and `type` is `Mesuré` (measured) or `Estimé` (estimated).

### Errors
Every error derives from `PyVeoliaIDFError`: `LoginError` (wrong credentials, or the login changed), `SessionExpiredError`, `RateLimitError`, `ServerError`, `UnexpectedResponseError` (the site has changed: the message names the field), `NotLoggedInError` and `UnknownContractError`.

## Design
The library has two layers, so that a change on the Veolia side stays in the lower one. See [docs/architecture.md](docs/architecture.md).

## Limitation
PyVeoliaIDF relies on how the Veolia customer area is built. It calls the backend methods of the pages, and any change there may break this library. The library validates every answer and raises an `UnexpectedResponseError` that names what changed, rather than returning wrong data.

## Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

Please make sure to update tests as appropriate: the unit tests must stay offline, and what needs the real site belongs to the integration tests.

## License
[MIT](https://choosealicense.com/licenses/mit/)

## Project status
PyVeoliaIDF has been initiated for integration with [Home Assistant](https://www.home-assistant.io/).
