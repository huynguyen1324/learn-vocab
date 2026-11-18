"""List models using config.json; standalone, no database or local module imports."""
import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[1] / "config.json")
    args = parser.parse_args(argv)
    secret = ""
    try:
        config = json.loads(args.config.read_text(encoding="utf-8-sig"))
        if not isinstance(config, dict):
            raise ValueError("Config must be a JSON object.")
        for key in ("BASE_URL", "API_KEY"):
            if not isinstance(config.get(key), str) or not config[key].strip():
                raise ValueError(f"Missing or empty {key}.")
            config[key] = config[key].strip()
        secret = config["API_KEY"]
        base = config["BASE_URL"].rstrip("/")
        url = urlsplit(base)
        if url.scheme not in {"http", "https"} or not url.netloc or url.username or url.password or url.query or url.fragment:
            raise ValueError("BASE_URL must be an HTTP(S) API root, e.g. https://host/v1.")
        request = Request(base + "/models", headers={
            "Authorization": "Bearer " + secret,
            "Accept": "application/json",
            "User-Agent": "learn-vocab/1.0",
        })
        with urlopen(request, timeout=90) as response:
            result = json.load(response)
        models = result.get("data") if isinstance(result, dict) else None
        if not isinstance(models, list) or any(not isinstance(row, dict) or not isinstance(row.get("id"), str) for row in models):
            raise ValueError("API response must contain data with model IDs.")
        for model in models:
            print(model["id"].replace(secret, "[REDACTED]"))
    except HTTPError as error:
        detail = " (models endpoint may be unsupported)" if error.code in {404, 405} else ""
        print(f"Model check failed: HTTP {error.code}{detail}.", file=sys.stderr)
        return 1
    except (URLError, TimeoutError):
        print("Model check failed: network error or timeout.", file=sys.stderr)
        return 1
    except (OSError, ValueError, UnicodeError) as error:
        detail = str(error).replace(secret, "[REDACTED]") if secret else str(error)
        print(f"Model check failed: {detail}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
