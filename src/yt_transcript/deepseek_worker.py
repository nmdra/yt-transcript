"""Private one-completion helper. Credentials are inherited, never serialized."""

import json
import signal
import sys
from dataclasses import asdict

from .deepseek_backend import INPUT_LIMIT, complete_http, validate_request
from .errors import FormattingError, classify_deepseek_failure
from .json_tools import strict_json_loads


def main() -> int:
    def terminate(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, terminate)
    try:
        raw = sys.stdin.buffer.read(INPUT_LIMIT + 1)
        if len(raw) > INPUT_LIMIT:
            raise ValueError
        payload = validate_request(strict_json_loads(raw.decode("utf-8")))
        envelope = {"text": complete_http(payload)}
    except FormattingError as exc:
        envelope = {"error": asdict(exc.info)}
    except ValueError, UnicodeError:
        envelope = {
            "error": asdict(classify_deepseek_failure("DEEPSEEK_OUTPUT_INVALID").info)
        }
    except KeyboardInterrupt:
        return 130
    except Exception:
        envelope = {"error": asdict(classify_deepseek_failure().info)}
    sys.stdout.buffer.write(json.dumps(envelope, ensure_ascii=False).encode("utf-8"))
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
