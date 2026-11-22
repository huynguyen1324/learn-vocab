"""Export the old vocabulary table as English/Vietnamese text pairs. Does not change DB."""
import argparse
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent


def export_vocabulary(database=ROOT / "instance" / "vocabulary.sqlite3", output=TOOLS / "input_vocab.txt"):
    from app import connect_database, create_app
    output = Path(output)
    database = Path(database)
    if database.exists() and database.is_file():
        db_url = f"sqlite:///{database.resolve().as_posix()}"
    else:
        db_url = create_app().config["DATABASE_URL"]
    if output.resolve() == database.resolve():
        raise ValueError("Export output must not overwrite the database.")
    db = connect_database(db_url)
    try:
        rows = db.execute("SELECT english, vietnamese FROM vocabulary ORDER BY id").fetchall()
    finally:
        db.close()
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
    parser.add_argument("--database", type=Path, default=ROOT / "instance" / "vocabulary.sqlite3", help="Read from this SQLite file if present; otherwise use DB_URL")
    parser.add_argument("--output", type=Path, default=TOOLS / "input_vocab.txt")
    args = parser.parse_args(argv)
    try:
        count = export_vocabulary(args.database, args.output)
        print(f"Exported {count} vocabulary entries to {args.output}.")
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Export failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
