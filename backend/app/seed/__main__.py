"""`make reset` runs `python -m app.seed` inside the backend container.

It asks the running API to reset itself, because only the API process can freeze
its own clock. The work happens in app.seed.reset.reset_demo().
"""

import urllib.error
import urllib.request

RESET_URL = "http://localhost:8000/demo/reset"


def main() -> None:
    request = urllib.request.Request(RESET_URL, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            print(response.read().decode())
    except urllib.error.HTTPError as error:
        raise SystemExit(f"Reset failed ({error.code}): {error.read().decode()}") from error
    except urllib.error.URLError as error:
        raise SystemExit(f"Backend not reachable at {RESET_URL}. Run `make up` first.") from error


if __name__ == "__main__":
    main()
