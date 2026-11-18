"""List models without touching the vocabulary database."""
import argparse
import sys

from ai_client import AIError, ROOT, list_models, load_ai_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=ROOT / "config.json")
    args = parser.parse_args()
    try:
        config = load_ai_config(args.config, require_model=False)
        for model in list_models(config):
            print(model.replace(config["API_KEY"], "[REDACTED]"))
    except (AIError, OSError, ValueError) as error:
        print(f"Model check failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
