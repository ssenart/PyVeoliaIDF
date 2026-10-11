import argparse
import asyncio
import getpass
import importlib.metadata
import json
import logging
import os
import sys
import traceback
from datetime import date

from pyveoliaidf.client import DEFAULT_LAST_N_DAYS, Client
from pyveoliaidf.model import Step

USERNAME_VARIABLE = "VEOLIAIDF_USERNAME"
PASSWORD_VARIABLE = "VEOLIAIDF_PASSWORD"


async def run(args: argparse.Namespace, username: str, password: str) -> object:
    async with Client(username, password, contract_number=args.contract, meter_number=args.meter) as client:
        if args.contracts:
            return [contract.model_dump(mode="json") for contract in await client.contracts()]

        history = await client.history(step=Step(args.step), start=args.start, end=args.end, last_n_days=args.days)

        return history.model_dump(mode="json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reads the water consumption from the Veolia Ile-de-France customer area."
    )
    parser.add_argument(
        "-u", "--username", help=f"Veolia IDF username (email). Default: ${USERNAME_VARIABLE}, then a prompt"
    )
    parser.add_argument(
        "-p",
        "--password",
        help=f"Veolia IDF password. It shows in the process list: prefer ${PASSWORD_VARIABLE}, or the prompt",
    )
    parser.add_argument(
        "-d", "--days", type=int, default=DEFAULT_LAST_N_DAYS, help="Days to read, up to the end (default 365)"
    )
    parser.add_argument(
        "--start", type=date.fromisoformat, help="First day (YYYY-MM-DD). Default: --days before the end"
    )
    parser.add_argument("--end", type=date.fromisoformat, help="Last day (YYYY-MM-DD). Default: today")
    parser.add_argument(
        "--step",
        choices=[step.value for step in Step],
        default=Step.DAY.value,
        help="One reading per day, week or month",
    )
    parser.add_argument("--contract", help="Contract number. Default: the first contract")
    parser.add_argument("--meter", help="Meter number. Default: the first meter of the contract")
    parser.add_argument(
        "--contracts", action="store_true", help="List the contracts and their meters instead of the readings"
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Log the calls and the retries to the standard error, for a bug report",
    )
    parser.add_argument(
        "--version", action="version", version=f"pyveoliaidf {importlib.metadata.version('pyveoliaidf')}"
    )

    return parser


def credentials(args: argparse.Namespace) -> tuple[str, str]:
    """Returns the username and the password: from the options, then from the environment, then from a prompt."""

    username = args.username or os.environ.get(USERNAME_VARIABLE) or input("Username: ")
    password = args.password or os.environ.get(PASSWORD_VARIABLE) or getpass.getpass("Password: ")

    return username, password


def main() -> int:
    """Main function"""
    args = build_parser().parse_args()
    if args.verbose:
        logging.basicConfig(
            level=logging.DEBUG, stream=sys.stderr, format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
        )
    username, password = credentials(args)

    try:
        result = asyncio.run(run(args, username, password))
    except Exception:  # noqa: BLE001 (the CLI reports any failure and exits)
        print(f"An error occured while querying pyveoliaidf library : {traceback.format_exc()}")
        return 1

    print(json.dumps(result, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
