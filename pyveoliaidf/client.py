import os
import time
import csv
from selenium import webdriver
from pyveoliaidf.enum import PropertyNameEnum

HOME_URL = 'https://espace-client.vedif.eau.veolia.fr'
LOGIN_URL = HOME_URL + '/s/login'
WELCOME_URL = HOME_URL + '/s/'
DATA_URL = HOME_URL + '/s/historique'
DATA_FILENAME = 'historique_jours_litres.csv'

DEFAULT_TMP_DIRECTORY = '/tmp'
DEFAULT_FIREFOX_WEBDRIVER = os.getcwd() + '/geckodriver'
DEFAULT_WAIT_TIME = 30

class LoginError(Exception):
    """ Client has failed to login in Veolia Web site (check username/password)"""
    pass

class Client(object):
    def __init__(self, username, password, firefox_webdriver_executable = DEFAULT_FIREFOX_WEBDRIVER, wait_time = DEFAULT_WAIT_TIME, tmp_directory = DEFAULT_TMP_DIRECTORY):
        self.__username = username
        self.__password = password
        self.__firefox_webdriver_executable = firefox_webdriver_executable
        self.__wait_time = wait_time        
        self.__tmp_directory = tmp_directory
        self.__data = []

    def data(self):
        return self.__data

    def update(self):

        # CSV is in the TMP directory
        data_file_path = self.__tmp_directory + '/' + DATA_FILENAME

        # We remove an eventual existing file (from a previous run that has not deleted it)
        if os.path.isfile(data_file_path):
           os.remove(data_file_path)

        # Initialize the Firefox WebDriver
        profile = webdriver.FirefoxProfile()
        options = webdriver.FirefoxOptions()
        options.headless = True
        profile.set_preference('browser.download.folderList', 2)  # custom location
        profile.set_preference('browser.download.manager.showWhenStarting', False)
        profile.set_preference('browser.helperApps.alwaysAsk.force', False)
        profile.set_preference('browser.download.dir', self.__tmp_directory)
        profile.set_preference('browser.helperApps.neverAsk.saveToDisk', 'text/csv')
        
        driver = webdriver.Firefox(executable_path=self.__firefox_webdriver_executable, firefox_profile=profile, options=options, service_log_path=self.__tmp_directory + '/geckodriver.log')
        try:
            driver.implicitly_wait(self.__wait_time)
            
            driver.get(HOME_URL)
            
            # Fill login form
            email_element = driver.find_element_by_css_selector("input[type='email']")
            password_element = driver.find_element_by_css_selector("input[type='password']")
            
            email_element.send_keys(self.__username)
            password_element.send_keys(self.__password)
            
            submit_button_element = driver.find_element_by_class_name('submit-button')
            submit_button_element.click()
            
            # Once we find the 'Historique' button from the main page, we are logged on successfully.
            try:
                historique_button_element = driver.find_element_by_xpath("//span[contains(.,'HISTORIQUE')]")
                historique_button_element.click()
            except:
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
            
            # Download file
            download_button_element = driver.find_element_by_xpath("//button[contains(.,'Télécharger la période')]")
            download_button_element.click()

            # Wait a few for the download to complete
            time.sleep(10)

            # Load the CSV file into the data structure
            with open(data_file_path, 'r') as csvfile:
                dictreader = csv.DictReader(csvfile, delimiter=';', fieldnames=[PropertyNameEnum.TIME.value, PropertyNameEnum.TOTAL_LITER.value, PropertyNameEnum.DAILY_LITER.value, PropertyNameEnum.TYPE.value])
                # Skip the header line
                next(dictreader.reader)
                for row in dictreader:
                    self.__data.append(dict(row))

            # Close the file
            csvfile.close()

            # Remove the file
            os.remove(data_file_path)
            
        finally:
            # Quit the driver
            driver.quit()
        

