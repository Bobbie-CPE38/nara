"""AU4 read-only acceptance probes. No reset, seed, real Offer or LLM call is sent.

The optional account login creates a session and logs it out in finally. Passwords,
cookies and response bodies are never printed. Real LINE smoke and reset checks remain
manual; a successful preflight is not a claim of full production acceptance.
"""

import argparse
import base64
import getpass
import http.cookiejar
import json
import urllib.error
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Gate:
    def __init__(self, base, user, password):
        self.base = base.rstrip("/")
        self.basic = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            NoRedirect(), urllib.request.HTTPCookieProcessor(self.jar)
        )
        self.failures = 0

    def request(self, method, path, *, basic=False, headers=None, body=None):
        h = {"Origin": self.base, **(headers or {})}
        if basic:
            h["Authorization"] = self.basic
        data = None if body is None else json.dumps(body).encode()
        if data is not None:
            h["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base + path, data=data, headers=h, method=method
        )
        try:
            response = self.opener.open(request, timeout=20)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read(1_000_000)
            try:
                payload = json.loads(raw)
            except (UnicodeError, ValueError):
                payload = None
            basic_challenge = (
                response.headers.get("WWW-Authenticate", "").lower().startswith("basic")
            )
            return response.code, basic_challenge, payload

    def check(self, label, method, path, wanted, *, challenge=False, **kwargs):
        code, basic, payload = self.request(method, path, **kwargs)
        ok = code in wanted and basic == challenge
        print(
            f"{'ok' if ok else 'FAIL'}  {label}: HTTP {code}, Basic challenge={basic}"
        )
        self.failures += not ok
        return payload

    def preflight(self, real_line):
        config = self.check("auth config", "GET", "/api/auth/config", {200})
        if not isinstance(config, dict) or config.get("auth_mode") != "session":
            print("FAIL  AWS must report AUTH_MODE=session")
            self.failures += 1
        for path in (
            "/",
            "/login",
            "/register",
            "/change-password",
            "/api/health",
            "/api/clock",
        ):
            self.check("public " + path, "GET", path, {200})
        for path in (
            "/api/dashboard",
            "/api/cases/1",
            "/api/cases/1/audit",
            "/api/me/offers",
            "/api/me/handovers",
            "/api/approvals",
            "/api/roster?staff_id=105",
            "/api/gap/shifts/1",
            "/api/auth/me",
        ):
            self.check("anonymous " + path, "GET", path, {401})
            self.check(
                "identity header cannot log in " + path,
                "GET",
                path,
                {401},
                headers={"X-Demo-User": "900"},
            )
        self.check(
            "Basic alone is not a session", "GET", "/api/dashboard", {401}, basic=True
        )
        for path in ("/demo", "/demo/control", "/demo/line-sim"):
            self.check("Demo gate " + path, "GET", path, {401}, challenge=True)
        for path in (
            "/api/demo/reset",
            "/api/demo/clock/advance",
            "/api/demo/clock/freeze",
            "/api/demo/clock/unfreeze",
            "/api/demo/attendance/check-in",
            "/api/demo/events",
        ):
            self.check(
                "Demo mutation gate " + path,
                "POST",
                path,
                {401},
                challenge=True,
                body={},
            )
        self.check("Demo page with Basic", "GET", "/demo/control", {200}, basic=True)
        self.check(
            "simulator needs a session too",
            "GET",
            "/api/demo/line-sim/offers?staff_id=105",
            {401},
            basic=True,
        )
        self.check(
            "events need a session too",
            "POST",
            "/api/demo/events",
            {401},
            basic=True,
            body={},
        )
        self.check(
            "wrong Demo password",
            "GET",
            "/demo/control",
            {401},
            challenge=True,
            headers={
                "Authorization": "Basic " + base64.b64encode(b"wrong:wrong").decode()
            },
        )
        for path in (
            "/api/internal/merge-windows/close-due",
            "/api/INTERNAL/merge-windows/close-due",
            "/api/%69nternal/merge-windows/close-due",
            "/api/docs",
            "/api/redoc",
            "/api/openapi.json",
        ):
            self.check("private " + path, "GET", path, {404}, basic=True)
        self.check(
            "webhook missing signature",
            "POST",
            "/api/line/webhook",
            {401} if real_line else {401, 503},
            body={"events": []},
        )
        for method, path in (
            ("GET", "/api/line/webhook"),
            ("POST", "/api/line/webhook?x=1"),
            ("POST", "/api/line/webhook/"),
            ("POST", "/api/line/webhooks"),
            ("POST", "/api/LINE/webhook"),
            ("POST", "/api//line/webhook"),
            ("POST", "/api/%6Cine/webhook"),
            ("POST", "/api/line/webhook%2F"),
            ("POST", "/api/line/webhook/../health"),
        ):
            self.check(
                "alternate webhook " + path, method, path, {404}, body={"events": []}
            )
        print(
            "LINE preflight only: signed Verify/Offer/Handover/check-in still need live verification"
        )

    def account(self, staff_id):
        password = getpass.getpass("Web account password (not Basic Auth): ")
        me = self.check(
            "web login",
            "POST",
            "/api/auth/login",
            {200},
            body={"staff_id": staff_id, "password": password},
        )
        password = None
        session_cookie = next(
            (cookie for cookie in self.jar if cookie.name == "nara_session"), None
        )
        old_cookie = (
            None if session_cookie is None else "nara_session=" + session_cookie.value
        )
        if (
            session_cookie is None
            or not session_cookie.has_nonstandard_attr("HttpOnly")
            or str(session_cookie.get_nonstandard_attr("SameSite", "")).lower() != "lax"
            or (self.base.startswith("https://") and not session_cookie.secure)
        ):
            print(
                "FAIL  session cookie must be Secure (HTTPS), HttpOnly and SameSite=Lax"
            )
            self.failures += 1
        try:
            if not isinstance(me, dict) or me.get("staff_id") != staff_id:
                self.failures += 1
                print("FAIL  login did not return the requested identity")
                return
            for path in (
                "/api/dashboard",
                "/api/me/offers",
                "/api/roster?staff_id=" + str(staff_id),
            ):
                self.check("logged in " + path, "GET", path, {200})
            identity = self.check(
                "identity header cannot change account",
                "GET",
                "/api/auth/me",
                {200},
                headers={"X-Demo-User": str(staff_id + 1)},
            )
            if not isinstance(identity, dict) or identity.get("staff_id") != staff_id:
                self.failures += 1
                print("FAIL  identity changed")
            self.check(
                "web accounts cannot report arbitrary events",
                "POST",
                "/api/events",
                {403},
                body={
                    "event_type": "PATIENT_SURGE",
                    "shift_id": 1,
                    "patient_count": 12,
                },
            )
            self.check(
                "own simulator",
                "GET",
                f"/api/demo/line-sim/offers?staff_id={staff_id}",
                {200},
                basic=True,
            )
            self.check(
                "other simulator identity forbidden",
                "GET",
                f"/api/demo/line-sim/offers?staff_id={staff_id + 1}",
                {403},
                basic=True,
            )
            self.check(
                "approval role",
                "GET",
                "/api/approvals",
                {403} if me.get("role") == "staff" else {200},
            )
        finally:
            self.check("logout", "POST", "/api/auth/logout", {204}, body={})
            self.check("logged out session", "GET", "/api/auth/me", {401})
            if old_cookie:
                self.check(
                    "revoked cookie cannot be replayed",
                    "GET",
                    "/api/auth/me",
                    {401},
                    headers={"Cookie": old_cookie},
                )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base")
    parser.add_argument("user")
    parser.add_argument(
        "password", nargs="?", help="legacy argv password; omit for a private prompt"
    )
    parser.add_argument("--require-real-line", action="store_true")
    parser.add_argument("--staff-id", type=int)
    args = parser.parse_args()
    url = urllib.parse.urlsplit(args.base)
    if (
        (
            url.scheme != "https"
            and not (
                url.scheme == "http" and url.hostname in ("127.0.0.1", "localhost")
            )
        )
        or url.path not in ("", "/")
        or url.query
        or url.fragment
        or url.username is not None
    ):
        parser.error(
            "Use an HTTPS origin (plain HTTP is allowed only on localhost for isolated tests)"
        )
    gate = Gate(
        args.base,
        args.user,
        args.password
        if args.password is not None
        else getpass.getpass("Demo Basic Auth password: "),
    )
    try:
        gate.preflight(args.require_real_line)
        if args.staff_id:
            gate.account(args.staff_id)
    except (OSError, ValueError):
        print("FAIL  request could not complete (details withheld)")
        return 1
    if gate.failures:
        print(f"{gate.failures} check(s) failed")
        return 1
    print("Automated checks passed; live AU4 checklist remains required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
