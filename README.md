# PyVeoliaIDF
PyVeoliaIDF is a Python library for getting water consumption from Veolia French provider.

Their water meter are wireless and transmit the consumption once per day.

All consumption data is available on the client account at Veolia Web Site (https://espace-client.vedif.eau.veolia.fr).

PyVeoliaIDF automatically go through the Web Site and download the consumption data CSV file, and make it available in a Python structure (list of dictionaries).

## Installation

### Requirements
PyVeoliaIDF is working with Selenium Python library to automate navigation through Veolia Web site. Selenium requires a WebDriver that acts as gateway between automatic actions from PyVeoliaIDF and a native browser already installed on the system.

PyVeoliaIDF has been developped and tested with Firefox browser (version 68.8) and its corresponding Web Driver geckodriver (version 0.24).

#### Firefox browser installation
Follow instructions [here](https://www.mozilla.org/fr/firefox/new)

#### Firefox Web Driver (geckodriver) installation
Follow instructions [here](https://github.com/mozilla/geckodriver/releases)

### Create your virtual environment
```bash
$ pip install virtualenv

$ cd /path/to/my_project_folder/

$ virtualenv venv
```

### PyVeoliaIDF installation
Use the package manager [pip](https://pip.pypa.io/en/stable/) to install PyVeoliaIDF.

```bash
pip install pyveoliaidf
```

You can also download the source code and install it manually.

```bash
cd /path/to/pyveoliaidf/
python setup.py install
```

## Usage

### Command line

```bash
$ pyveoliaidf -u 'your login' -p 'your password' -w 'path/to/Selenium Web Driver' -s 30 -t 'temporary directory where to store CSV file (ex: /tmp)'
```

### Library

```python
import pyveoliaidf

client = pyveoliaidf.Client('your login',
                         'your password',
                         365,
                         'path/to/Selenium Web Driver',
                         30,
                         'temporary directory where to store CSV file (ex: /tmp)')

client.update()

data = client.data()
```

### Output

```json
data =>
[
  {
    "time": "2019-07-14 19:00:00",
    "total_liter": "506669",
    "daily_liter": "530",
    "type": "Estim\u00c3\u00a9",
    "timestamp": "2019-08-31T16:55:01.236779"
  },
  {
    "time": "2019-07-15 19:00:00",
    "total_liter": "507523",
    "daily_liter": "854",
    "type": "Mesur\u00c3\u00a9",
    "timestamp": "2019-08-31T16:55:01.236779"
  },
  {
    "time": "2019-07-16 19:00:00",
    "total_liter": "508314",
    "daily_liter": "791",
    "type": "Mesur\u00c3\u00a9",
    "timestamp": "2019-08-31T16:55:01.236779"
  }
]
```

## Limitation
PyVeoliaIDF relies on how Veolia Web Site is built. It goes through each Web pages and automatically fill forms, click buttons using their internal identifiers.

Any change in the Web site structure or identifier naming may break this library.

We expect in close Future that Veolia makes available a standard API from which we can get safely their data.

## Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

Please make sure to update tests as appropriate.

## License
[MIT](https://choosealicense.com/licenses/mit/)

## Project status
PyVeoliaIDF has been initiated for integration with [Home Assistant](https://www.home-assistant.io/).
