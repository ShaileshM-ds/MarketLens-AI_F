"""Administration commands.

    python -m app.cli create-user --username alice --role admin
    python -m app.cli rebuild-summaries --mode imported
    echo "<password>" | python -m app.cli create-user --username alice --role admin --password-stdin

No default or shared credentials exist; every account is created here.
"""

import argparse
import getpass
import sys
from datetime import datetime, timezone

from pymongo import MongoClient

from marketlens_core.db import ensure_mode_indexes
from marketlens_core.explorer import rebuild_product_summaries
from marketlens_core.settings import DataMode, get_settings

from .auth import ROLES, hash_password

MIN_PASSWORD = 12


def create_user(args) -> int:
    username = args.username.strip().lower()
    if not username.isascii() or not username.replace("-", "").replace("_", "").isalnum():
        print("Username may contain only letters, digits, '-' and '_'.", file=sys.stderr)
        return 2
    if args.password_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Repeat password: "):
            print("Passwords don't match.", file=sys.stderr)
            return 2
    if len(password) < MIN_PASSWORD:
        print(f"Password must be at least {MIN_PASSWORD} characters.", file=sys.stderr)
        return 2
    settings = get_settings()
    client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=3000)
    users = client[settings.mongo_db_accounts].users
    if users.find_one({"_id": username}):
        print(f"User '{username}' already exists.", file=sys.stderr)
        return 1
    users.insert_one(
        {
            "_id": username,
            "username": username,
            "role": args.role,
            "password_hash": hash_password(password),
            "created_at": datetime.now(timezone.utc),
        }
    )
    print(f"Created {args.role} '{username}'.")
    return 0


def rebuild_summaries(args) -> int:
    """Rebuild the explorer read model. Reads products/offers/observations/reviews; writes only product_summaries."""
    settings = get_settings()
    mode = DataMode(args.mode)
    client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=3000, tz_aware=True)
    db = client[settings.database_for(mode)]
    ensure_mode_indexes(db)
    n = rebuild_product_summaries(db)
    print(f"Rebuilt {n} product summaries in {mode.value} ({settings.database_for(mode)}).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    cu = sub.add_parser("create-user", help="Create an account")
    cu.add_argument("--username", required=True)
    cu.add_argument("--role", choices=ROLES, default="consumer")
    cu.add_argument("--password-stdin", action="store_true", help="Read the password from standard input")
    rs = sub.add_parser("rebuild-summaries", help="Rebuild the Product Explorer read model for one mode")
    rs.add_argument("--mode", choices=[m.value for m in DataMode], required=True)
    args = parser.parse_args()
    return {"create-user": create_user, "rebuild-summaries": rebuild_summaries}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
