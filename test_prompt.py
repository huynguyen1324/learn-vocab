"""Send Hello using the configured AI model; does not touch the database."""
import argparse
import sys

from ai_client import AIError, ROOT, chat, load_ai_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=ROOT / "config.json")
    args = parser.parse_args()
    try:
        config = load_ai_config(args.config)
        answer = chat(config, [{"role": "user", "content": "Hello"}])
        print(answer.replace(config["API_KEY"], "[REDACTED]"))
    except (AIError, OSError, ValueError) as error:
        print(f"Prompt test failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
