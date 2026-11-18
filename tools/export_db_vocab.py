"""Export the old vocabulary table as English/Vietnamese text pairs. Does not change DB."""
import argparse
import sqlite3
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent


def export_vocabulary(database=ROOT / "instance" / "vocabulary.sqlite3", output=TOOLS / "input_vocab.txt"):
    database, output = Path(database).resolve(), Path(output)
    if output.resolve() == database:
        raise ValueError("Export output must not overwrite the database.")
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
        rows = db.execute("SELECT english, vietnamese FROM vocabulary ORDER BY id").fetchall()
    for row in rows:
        if any(not isinstance(value, str) or not value.strip() or "\n" in value or "\r" in value for value in row):
            raise ValueError("Cannot export blank/multiline fields into line-pair format.")
    content = "\n\n".join(f"{english}\n{vietnamese}" for english, vietnamese in rows)
    if content:
        content += "\n"
    if output.exists():
        backup = output.with_name(output.name + ".before-export-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
        backup.write_bytes(output.read_bytes())
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(output)
    return len(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "instance" / "vocabulary.sqlite3")
    parser.add_argument("--output", type=Path, default=TOOLS / "input_vocab.txt")
    args = parser.parse_args(argv)
    try:
        count = export_vocabulary(args.database, args.output)
        print(f"Exported {count} vocabulary entries to {args.output}.")
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"Export failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
