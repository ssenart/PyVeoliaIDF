import os
import time
import csv
import logging
import datetime
from pyveoliaidf.enum import PropertyNameEnum
from pyveoliaidf.webdriverwrapper import WebDriverWrapper
from typing import Any


HOME_URL = 'https://espace-client.vedif.eau.veolia.fr'
LOGIN_URL = HOME_URL + '/s/login'
WELCOME_URL = HOME_URL + '/s/'
DATA_URL = HOME_URL + '/s/historique'
DATA_FILENAME = 'historique_jours_litres.csv'

DEFAULT_TMP_DIRECTORY = '/tmp'
DEFAULT_FIREFOX_WEBDRIVER = os.getcwd() + '/geckodriver'
DEFAULT_WAIT_TIME = 30
DEFAULT_LAST_N_DAYS = 365

Logger = logging.getLogger(__name__)


class LoginError(Exception):
    """ Client has failed to login in Veolia Web site (check username/password)"""
    pass


class Client(object):

    def __init__(self, username, password, lastNDays: int = DEFAULT_LAST_N_DAYS, firefox_webdriver_executable=DEFAULT_FIREFOX_WEBDRIVER, wait_time=DEFAULT_WAIT_TIME, tmp_directory=DEFAULT_TMP_DIRECTORY):
        self.__username = username
        self.__password = password
        self.__firefox_webdriver_executable = firefox_webdriver_executable
        self.__wait_time = wait_time
        self.__tmp_directory = tmp_directory
        self.__lastNDays = lastNDays
        self.__data = []

    def data(self) -> list[dict[str, Any]]:
        return self.__data

    def update(self):

        Logger.debug("Start updating the data...")

        # CSV is in the TMP directory
        data_file_path = self.__tmp_directory + '/' + DATA_FILENAME

        # We remove an eventual existing file (from a previous run that has not deleted it)
        if os.path.isfile(data_file_path):
            os.remove(data_file_path)

        # Create the WebDriver with the ability to log and take screenshot for debugging.
        driver = WebDriverWrapper(self.__firefox_webdriver_executable, self.__wait_time, self.__tmp_directory, True)

        try:
            # Go to login page.
            driver.get(HOME_URL, "Go to VeoliaIDF login page")

            # Fill login form.
            email_element = driver.find_element_by_css_selector("input[inputmode='email']", "Login page: Email text field")
            password_element = driver.find_element_by_css_selector("input[type='password']", "Login page: Password text field")

            email_element.send_keys(self.__username)
            password_element.send_keys(self.__password)

            submit_button_element = driver.find_element_by_class_name('submit-button', "Login page: 'Valider' button")
            submit_button_element.click()

            # Once we find the 'Historique' button from the main page, we are logged on successfully.
            try:
                historique_button_element = driver.find_element_by_xpath("//span[contains(.,'HISTORIQUE')]", "Welcome page: 'Historique' menu item")
                historique_button_element.click()
            except Exception:
                # Perhaps, login has failed.
                if driver.current_url == WELCOME_URL:
                    # We're good.
                    pass
                elif driver.current_url.startswith(LOGIN_URL):
                    raise LoginError("Veolia sign in has failed, please check your username/password")
                else:
                    raise

            # Wait a few for the data page load to complete
            time.sleep(5)

            # Click on the "Jours" button.
            jours_button_element = driver.find_element_by_xpath("//lightning-button-group[2]/div/slot/c-icl-button-stateful[1]/button", "Historique page: 'Jours' button")
            jours_button_element.click()

            # Wait a few for some internal refreshes.
            time.sleep(10)

            # Click on the "Litres" button.
            litres_button_element = driver.find_element_by_xpath("//lightning-button-group[3]/div/slot/c-icl-button-stateful[2]/button", "Historique page: 'Litres' button")
            litres_button_element.click()

            # Wait a few for some internal refreshes.
            time.sleep(10)

            # Compute start and end dates.
            dateFormat = "%d/%m/%Y"
            endDate = datetime.date.today()
            startDate = endDate + datetime.timedelta(days=-self.__lastNDays)

            # Fill the start date text field.
            start_date_element = driver.find_element_by_xpath("//input[@id='input-52']", "Historique page: 'Start date' text field")
            start_date_element.clear()
            start_date_element.send_keys(startDate.strftime(dateFormat))

            # Fill the end date text field.
            end_date_element = driver.find_element_by_xpath("//input[@id='input-56']", "Historique page: 'End date' text field")
            end_date_element.clear()
            end_date_element.send_keys(endDate.strftime(dateFormat))

            # Wait a few for some internal refreshes.
            time.sleep(10)

            # Download file
            download_button_element = driver.find_element_by_xpath("//button[contains(.,'Télécharger la période')]", "Historique page: 'Télécharger la période' button")
            download_button_element.click()

            # Timestamp of the data.
            data_timestamp = datetime.datetime.now().isoformat()

            # Wait a few for the download to complete.
            time.sleep(10)

            Logger.debug("Loading data...")

            # Load the CSV file into the data structure.
            with open(data_file_path, 'r', encoding="utf-8-sig") as csvfile:
                dictreader = csv.DictReader(csvfile, delimiter=';', fieldnames=[PropertyNameEnum.TIME.value, PropertyNameEnum.TOTAL_LITER.value, PropertyNameEnum.DAILY_LITER.value, PropertyNameEnum.TYPE.value])
                # Skip the header line
                # next(dictreader.reader)
                for row in dictreader:
                    row[PropertyNameEnum.TIMESTAMP.value] = data_timestamp
                    self.__data.append(dict(row))

            # Ensure the data we get is the data we ask.
            header = self.__data[0]
            if header[PropertyNameEnum.TOTAL_LITER.value] != "Index relevé (litres)" or header[PropertyNameEnum.DAILY_LITER.value] != "Consommation du jour (litres)":
                errorMessage = f"The data file {data_file_path} does not contain the expected columns 'Index relevé (litres)' and 'Consommation du jour (litres)'. Instead, we have '{header[PropertyNameEnum.TOTAL_LITER.value]}' and '{header[PropertyNameEnum.DAILY_LITER.value]}'."
                Logger.warning(errorMessage)
                raise Exception(errorMessage)

            # Remove the header from the data.
            del (self.__data[0])

            # Remove the file
            os.remove(data_file_path)

            Logger.debug("The data update terminates normally")

        except Exception:
            Logger.error("An unexpected error occured while updating the data", exc_info=True)
            raise
        finally:
            # Close the file
            csvfile.close()

            # Quit the driver
            driver.quit()
