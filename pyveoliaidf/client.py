import os
from selenium import webdriver
import time
import csv

HOME_URL = 'https://espace-client.vedif.eau.veolia.fr'
LOGIN_URL = HOME_URL + '/s/login'
DATA_URL = HOME_URL + '/s/historique'
DATA_FILENAME = 'historique_jours_litres.csv'

DEFAULT_TMP_DIRECTORY = '/tmp'
DEFAULT_FIREFOX_WEBDRIVER = os.getcwd() + '/geckodriver'

class Client(object):
    def __init__(self, username, password, firefox_webdriver_executable = DEFAULT_FIREFOX_WEBDRIVER, tmp_directory = DEFAULT_TMP_DIRECTORY):
        self.__username = username
        self.__password = password
        self.__firefox_webdriver_executable = firefox_webdriver_executable
        self.__tmp_directory = tmp_directory
        self.data = []

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
        
        driver = webdriver.Firefox(executable_path=self.__firefox_webdriver_executable, firefox_profile=profile, options=options)
        driver.set_window_position(0, 0)
        driver.set_window_size(1200, 1200)
        
        driver.implicitly_wait(10)
        
        driver.get(HOME_URL)
        
        # Fill login form
        email_element = driver.find_element_by_css_selector("input[type='email']")
        password_element = driver.find_element_by_css_selector("input[type='password']")
        
        email_element.send_keys(self.__username)
        password_element.send_keys(self.__password)
        
        submit_button_element = driver.find_element_by_class_name('submit-button')
        submit_button_element.click()
        
        # Wait a few for the login to complete
        time.sleep(5)
        
        # Page 'votre consomation'
        driver.get(DATA_URL)

        # Wait a few for the data page load to complete
        time.sleep(10)
        
        # Download file
        download_button_element = driver.find_element_by_xpath("//button[contains(.,'Télécharger la période')]")
        download_button_element.click()
        
        # Wait a few for the download to complete
        time.sleep(10)
        
        # Close the driver
        driver.close()
        
        # Load the CSV file into the data structure
        with open(data_file_path, 'r') as csvfile:
            dictreader = csv.DictReader(csvfile, delimiter=';', fieldnames=['time', 'total_liter', 'daily_liter', 'type'])
            # Skip the header line
            next(dictreader.reader)
            for row in dictreader:
                self.data.append(dict(row))

        # Close the file
        csvfile.close()

        # Remove the file
        os.remove(data_file_path)
