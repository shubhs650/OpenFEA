"""Explicit local migration command. Downgrades remove schema/data: back up first."""

import argparse

from app.config import Settings
from app.persistence.database import Database


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("direction", choices=("upgrade", "downgrade"))
    parser.add_argument("target", help="head, base, or a specific revision")
    arguments = parser.parse_args()
    settings = Settings.from_environment()
    database = Database(settings.data_root / "metadata.sqlite3")
    try:
        database.migrate(arguments.target, downgrade=arguments.direction == "downgrade")
    finally:
        database.close()
    print("Migration completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
