"""Count word frequency across collocation english fields; read-only, never changes DB."""
import argparse
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent

WORD_PATTERN = re.compile(r"[a-z0-9']+")

STOPWORDS = frozenset({
    "a", "an", "the", "to", "of", "for", "on", "in", "up", "out", "off",
    "be", "is", "are", "was", "were", "been", "being",
    "and", "or", "with", "at", "by", "from", "as", "into", "over",
    "after", "before", "it", "its", "this", "that",
})


def count_words(database=ROOT / "instance" / "vocabulary.sqlite3"):
    from app import create_app, connect_database
    database = Path(database)
    configured_url = create_app().config["DATABASE_URL"]
    db_url = f"sqlite:///{database.resolve().as_posix()}" if configured_url.startswith("sqlite:///") or database.exists() else configured_url
    db = connect_database(db_url)
    try:
        rows = db.execute("SELECT english FROM collocations").fetchall()
    finally:
        db.close()
    counts = Counter()
    for (english,) in rows:
        counts.update(w for w in WORD_PATTERN.findall(english.lower()) if w not in STOPWORDS)
    return counts, len(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "instance" / "vocabulary.sqlite3", help="Read from this SQLite file if present; otherwise use DB_URL")
    parser.add_argument("--output", type=Path, default=TOOLS / "word_count_statistic.txt")
    args = parser.parse_args(argv)
    try:
        counts, total = count_words(args.database)
        lines = [f"{word}: {counts[word]}" for word in sorted(counts, key=lambda w: (-counts[w], w))]
        args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Counted {len(counts)} distinct words from {total} collocations -> {args.output}.")
    except (OSError, RuntimeError) as error:
        print(f"Count failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
