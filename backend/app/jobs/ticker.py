"""The job service of docker-compose.yml: `python -m app.jobs.ticker`.

Every JOB_INTERVAL_SECONDS (default 30) it calls one internal route of the
backend. It decides nothing itself: the backend judges what is due with its own
clock, which a demo can freeze and this process cannot see (docs/workflow.md,
section 3.8).

Standard library only, and no import from the rest of `app`: this container
installs nothing and has no database settings.
"""

import http.client
import os
import time
import urllib.error
import urllib.request

CLOSE_DUE_PATH = "/internal/merge-windows/close-due"
SECRET_HEADER = "X-Internal-Secret"


def tick(url: str, secret: str) -> str:
    """Call the route once and describe what happened. A failed call does not raise.

    That includes a backend that restarts in the middle of a call: the job
    must outlive it and try again on the next round.
    """
    request = urllib.request.Request(url, method="POST", headers={SECRET_HEADER: secret})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return f"{response.status} {response.read().decode()}"
    except urllib.error.HTTPError as error:
        return f"failed ({error.code}): {error.read().decode()}"
    # OSError covers URLError, timeouts and a reset connection. HTTPException
    # covers a connection closed without an answer (RemoteDisconnected)
    except (OSError, http.client.HTTPException) as error:
        return f"backend not reachable: {type(error).__name__}: {error}"


def interval_seconds(value: str) -> float:
    """Seconds between two calls. Zero or less would spin, so it stops the job."""
    try:
        seconds = float(value)
    except ValueError:
        raise SystemExit(f"JOB_INTERVAL_SECONDS must be a number, got {value!r}") from None
    # `not >=` also rejects NaN
    if not seconds >= 1 or seconds == float("inf"):
        raise SystemExit(f"JOB_INTERVAL_SECONDS must be 1 or more, got {value!r}")
    return seconds


def main() -> None:
    secret = os.environ.get("INTERNAL_JOB_SECRET")
    if not secret:
        raise SystemExit("INTERNAL_JOB_SECRET is not set")
    url = os.environ.get("BACKEND_URL", "http://backend:8000").rstrip("/") + CLOSE_DUE_PATH
    interval = interval_seconds(os.environ.get("JOB_INTERVAL_SECONDS", "30"))
    while True:
        print(f"{CLOSE_DUE_PATH}: {tick(url, secret)}", flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    main()
