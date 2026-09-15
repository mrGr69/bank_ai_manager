from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.db import SessionLocal, init_db
from app.seed import seed
from app.services.files import import_path


ROOT = Path(__file__).resolve().parents[1]


async def cmd_seed() -> None:
    await seed()
    print("seed ok")


async def cmd_import() -> None:
    await init_db()
    await seed()
    files = list(ROOT.glob("*.xls")) + list(ROOT.glob("*.xlsx"))
    if not files:
        print("немає xls/xlsx у корені проєкту")
        return
    async with SessionLocal() as session:
        for path in files:
            if path.name.startswith("~$"):
                continue
            print("import", path.name)
            result = await import_path(session, path)
            print(" ", result.get("kind"), "inserted", result["inserted"], "skipped", result["skipped"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["seed", "import-history"])
    args = parser.parse_args()
    if args.command == "seed":
        asyncio.run(cmd_seed())
    else:
        asyncio.run(cmd_import())


if __name__ == "__main__":
    main()
