# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.1.12]: https://github.com/ssenart/PyVeoliaIDF/compare/0.1.11...0.1.12
[0.1.11]: https://github.com/ssenart/PyVeoliaIDF/compare/0.1.10...0.1.11
[0.1.10]: https://github.com/ssenart/PyVeoliaIDF/compare/0.1.9...0.1.10
[0.1.9]: https://github.com/ssenart/PyVeoliaIDF/compare/0.1.8...0.1.9
[0.1.8]: https://github.com/ssenart/PyVeoliaIDF/compare/0.1.7...0.1.8
