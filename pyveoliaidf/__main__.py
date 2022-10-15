import argparse
import sys
import json
import traceback

from pyveoliaidf.client import Client


def main():
    """Main function"""
    parser = argparse.ArgumentParser()
    parser.add_argument("-u", "--username",
                        required=True,
                        help="Veolia IDF username (email)")
    parser.add_argument("-p", "--password",
                        required=True,
                        help="Veolia IDF password")
    parser.add_argument("-w", "--webdriver",
                        required=True,
                        help="Firefox webdriver executable (geckodriver)")
    parser.add_argument("-s", "--wait_time",
                        required=False,
                        type=int,
                        default=30,
                        help="Wait time in seconds (see https://selenium-python.readthedocs.io/waits.html for details)")
    parser.add_argument("-t", "--tmpdir",
                        required=False,
                        help="tmp directory (default is /tmp)")

    args = parser.parse_args()

    client = Client(args.username, args.password, 365, args.webdriver, args.wait_time, args.tmpdir)

    try:
        client.update()
    except BaseException:
        print('An error occured while querying PyVeoliaIDF library : %s', traceback.format_exc())
        return 1

    print(json.dumps(client.data(), indent=2))


if __name__ == '__main__':
    sys.exit(main())
