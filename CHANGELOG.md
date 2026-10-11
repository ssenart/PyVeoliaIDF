# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- **Breaking:** the library no longer drives a browser. It calls the Salesforce Aura backend of the customer area over HTTPS, so Firefox, geckodriver and Selenium are no longer needed.
- **Breaking:** the client is asynchronous: `await client.update()`, `await client.load_since(days)`, and `async with Client(...) as client`. The command-line tool is unchanged apart from its options.
- The volumes of `data()` are integers (liters), not text. The keys are the same.
- The code is split into a transport (`aura.py`), the Veolia API (`api_client.py`, `veolia_models.py`) and the public client (`client.py`, `model.py`).
- The package is under `src/pyveoliaidf`.
- The code is formatted with `ruff format` and typed with `mypy --strict`, tests included.
- CI is aligned with PyGazpar: lint (ruff format, ruff check, mypy) and tests run inline in `ci.yaml` on Python 3.10 to 3.14 (default 3.14), with `setup-uv` caching and `--locked`. The `python-lint` and `python-test` composite actions are removed, Firefox is no longer installed, and the live tests run once per CI run when the `VEOLIAIDF_*` secrets are set.

### Added
- `Client.load_since()` and `Client.load_date_range()` return `DailyReading` models; `Client.get_contract_ids()` lists the contracts, and `contract_id=` selects one.
- `build_ssl_context()` is exported, for callers that give their own HTTP session: it trusts the intermediate certificate that the site leaves out.
- A typed error hierarchy rooted at `PyVeoliaIDFError`, with `UnexpectedResponseError` naming the field that changed.
- Retries with backoff, a re-login when the session ends (once for concurrent calls), and a bundled intermediate certificate for the site.
- The runtime dependencies have loose lower bounds (`aiohttp>=3.10`, `certifi>=2023.7.22`, `pydantic>=2.10`), so the library installs next to Home Assistant, which pins its own versions.
- Offline unit tests (95% coverage gate with `--cov`, property-based tests with `hypothesis`) and opt-in live tests (`pytest -m integration`).
- Dependabot for the Python dependencies and the GitHub Actions.

### Deprecated
- The old positional arguments `firefox_webdriver_executable`, `firefox_binary_location`, `wait_time` and `tmp_directory` of `Client` are accepted and ignored, with a `DeprecationWarning`.

### Removed
- `-w/--webdriver`, `-s/--wait_time` and `-t/--tmpdir` of the command-line tool, and the `selenium` and `openpyxl` dependencies.

## [0.4.6a1] - 2026-10-04

### Added
- The client logs how many records it retrieved, and the period they cover.

### Changed
- Selenium is required as `>=4.50.0` (was pinned to `4.17.2`). Selenium 4.50 requires Python 3.10 or newer, so Python 3.9 is no longer supported.
- geckodriver is found or downloaded by Selenium Manager, which ships with Selenium, when no driver path is given. The `-w/--webdriver` option is optional, and the bundled `drivers/` folder has been removed.
- The "Consulter l'historique" button is located by its text instead of a fixed XPath.
- The project is managed with uv: `pyproject.toml` (hatchling build, `dev` dependency group) and `uv.lock`. The version is set in `pyproject.toml`, and `pyveoliaidf.__version__` is read from the installed package metadata.
- The GitHub workflows are rewritten: CI runs on pushes and pull requests, and releases are created manually with version checks and PyPI trusted publishing. The automatic TestPyPI publish on every push is removed.
- The README describes the uv development setup and the Selenium Manager driver.

### Fixed
- Selenium 4.50 no longer accepts `log_path`, so the geckodriver log is written with `log_output` again.
- The command-line tool passed its arguments to `Client` in the wrong order, so the wait time was used as the Firefox binary path and the temporary directory was ignored.

### Removed
- `setup.py`, `setup.cfg`, `requirements.txt`, `MANIFEST.in`, `version.py` and `updateVersion.py`, replaced by `pyproject.toml` and the uv tooling.
- The `requests` development dependency, which was not used.

## [0.4.5] - 2025-10-06

### Fixed
[#7](https://github.com/ssenart/PyVeoliaIDF/issues/7): The site "L'eau d'Ile de France" has some button identifier changed.

## [0.4.4] - 2025-06-15

### Fixed
[#6](https://github.com/ssenart/PyVeoliaIDF/issues/6): The site "L'eau d'Ile de France" login page has been changed.

## [0.4.3] - 2025-05-25

### Fixed
[#5](https://github.com/ssenart/PyVeoliaIDF/issues/5): The site "L'eau d'Ile de France" structure has been changed.

## [0.4.2] - 2025-04-10

### Fixed
[#4](https://github.com/ssenart/PyVeoliaIDF/issues/4): Login failure.

## [0.4.1] - 2025-01-13

### Fixed
[#3](https://github.com/ssenart/PyVeoliaIDF/issues/3): The new site "L'eau d'Ile de France" structure has been changed.

## [0.4.0] - 2025-01-02

### Fixed
[#2](https://github.com/ssenart/PyVeoliaIDF/issues/2): Migration from "Veolia Ile de France" to "L'eau d'Ile de France".

## [0.3.4] - 2024-01-27

### Fixed
- Set the correct firefox location for Linux.

## [0.3.3] - 2024-01-27

### Fixed
- Fix wrong Selenium version in setup.cfg.

## [0.3.2] - 2024-01-27

### Fixed
- Add Python 3.11 and 3.12 support.

## [0.3.1] - 2024-01-27

### Fixed
- Fix lint error: W291 trailing whitespace

## [0.3.0] - 2024-01-27

### Fixed
- The Web site has changed some component xpath.

### Changed
- Upgrade Selenium version to 4.17.2
- Upgrade Geckodriver version to 0.34.0

## [0.2.1] - 2023-02-05

### Fixed
- The Web site has changed some component xpath. 

## [0.2.0] - 2022-10-17

### Added 
- Add a new parameter 'lastNDays' that permits to control how many days of data we want to retrieve.

### Fixed
- Add some means that permits to log every Selenium actions.
- Add some controls on the downloaded data file (check its content) before processing it.

## [0.1.13] - 2021-12-03
### Fixed
- Increase waiting time after selection of 'Jours' and 'Litres' buttons. Sometimes, we get only a partial set of data with missing most recent ones.

## [0.1.12] - 2020-10-12
### Fixed
- The Veolia login email text box has changed its identifier.

## [0.1.11] - 2020-10-03
### Fixed
- After simulating clicks on the 'Jours' and 'Litres' buttons, we have to wait a few (5 seconds) for internal form refresh. Otherwise, we got an inconsistent data file.

## [0.1.10] - 2020-10-03
### Fixed
- The VeoliaIDF web site has changed and added some buttons to select the consumption period and the consumption unit.

## [0.1.9] - 2019-08-31
### Fixed
- WebDriver window size must be large enough to display all clickable components.

## [0.1.8] - 2019-08-31
### Added
- Use PropertyNameEnum type to store all property names.
- Add LoginError exception raised when PyVeoliaIDF is unable to sign in the Veolia Web site with the given username/password.
- Add timestamp property that contains date/time when the data has been retrieved.

[Unreleased]: https://github.com/ssenart/PyVeoliaIDF/compare/0.4.6a1...HEAD
[0.4.6a1]: https://github.com/ssenart/PyVeoliaIDF/compare/0.4.5...0.4.6a1
[0.1.12]: https://github.com/ssenart/PyVeoliaIDF/compare/0.1.11...0.1.12
[0.1.11]: https://github.com/ssenart/PyVeoliaIDF/compare/0.1.10...0.1.11
[0.1.10]: https://github.com/ssenart/PyVeoliaIDF/compare/0.1.9...0.1.10
[0.1.9]: https://github.com/ssenart/PyVeoliaIDF/compare/0.1.8...0.1.9
[0.1.8]: https://github.com/ssenart/PyVeoliaIDF/compare/0.1.7...0.1.8
