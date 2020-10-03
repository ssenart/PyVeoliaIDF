import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
  name = 'pyveoliaidf',
  version = '0.1.11',
  author = 'Stephane Senart',
  author_email = 'stephane.senart@gmail.com',
  description = 'Retrieve water consumption from Veolia Ile-de-France web site (French Water Company)',
  long_description=long_description,
  long_description_content_type="text/markdown",
  url = 'https://github.com/ssenart/PyVeoliaIDF',
  packages=setuptools.find_packages(),
  classifiers=[
    'Development Status :: 3 - Alpha',      # Choose either "3 - Alpha", "4 - Beta" or "5 - Production/Stable" as the current state of your package    'Intended Audience :: Developers',      # Define that your audience are developers
    'Topic :: Software Development :: Build Tools',
    'License :: OSI Approved :: MIT License',
    'Operating System :: OS Independent',    
    'Programming Language :: Python :: 3.7',    
  ],
  python_requires='>=3.7',
  download_url = 'https://github.com/ssenart/pyveoliaidf/releases/tag/0.1.11',
  keywords = ['Resource', 'Water', 'Consumption', 'Veolia', 'Ile-de-France'],
  entry_points={
    'console_scripts': [
        'pyveoliaidf = pyveoliaidf.__main__:main'
    ]
  },
  install_requires=[
    'selenium == 3.141',
    'openpyxl == 2.6.3'
  ],
  license='MIT',
)

