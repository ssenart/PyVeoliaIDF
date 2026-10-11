import argparse
import asyncio
import json
import sys
import traceback

from pyveoliaidf.client import Client


async def run(username: str, password: str, last_n_days: int) -> list[dict[str, object]]:
    async with Client(username, password, last_n_days) as client:
        await client.update()

        return client.data()


def main() -> int:
    """Main function"""
    parser = argparse.ArgumentParser()
    parser.add_argument("-u", "--username", required=True, help="Veolia IDF username (email)")
    parser.add_argument("-p", "--password", required=True, help="Veolia IDF password")
    parser.add_argument(
        "-d", "--days", required=False, type=int, default=365, help="Number of days to load (default is 365)"
    )

    args = parser.parse_args()

    try:
        data = asyncio.run(run(args.username, args.password, args.days))
    except Exception:  # noqa: BLE001 (the CLI reports any failure and exits)
        print(f"An error occured while querying PyVeoliaIDF library : {traceback.format_exc()}")
        return 1

    print(json.dumps(data, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
