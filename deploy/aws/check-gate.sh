#!/usr/bin/env bash
# Checks the Basic Auth gate of the AWS test machine from outside
# (round 6 PR D, docs/workflow.md 6.30; the rule: every path needs the login except
# the exact request `POST /api/line/webhook`).
#
#   deploy/aws/check-gate.sh https://<SITE_DOMAIN> <user> <password>
#
# A 401 from the gate carries "WWW-Authenticate: Basic". The webhook's own 401
# (bad LINE signature) does not, which is how the two are told apart.
#
# `/demo/*` pages and `/api/demo/*` routes are NOT blocked: they work with the login
# (the Demo control page calls them from the browser), and without it they get 401.

set -uo pipefail
shopt -s extglob

base="${1:?Usage: check-gate.sh <base url> <user> <password>}"
user="${2:?Usage: check-gate.sh <base url> <user> <password>}"
password="${3:?Usage: check-gate.sh <base url> <user> <password>}"
# --path-as-is: send "//", "/../" and "%6C" as written, so a path that only works
# after curl tidied it up cannot hide a hole. A first page load of the dev server
# compiles the page, hence the generous time limit.
curl_options=(--silent --output /dev/null --max-time 60 --path-as-is)
failures=0

# Prints "<status> gate" when the gate answered, "<status> passed" otherwise
probe() {
  local method="$1" path="$2" auth="$3" headers status
  local args=("${curl_options[@]}" --request "$method" --dump-header - --write-out '%{http_code}')
  case "$auth" in
    with-login) args+=(--user "$user:$password") ;;
    wrong-login) args+=(--user "$user:not-$password") ;;
  esac
  if [ "$method" = "POST" ]; then
    args+=(--header "Content-Type: application/json" --data '{"events":[]}')
  fi
  headers="$(curl "${args[@]}" "$base$path")"
  status="${headers: -3}"
  if grep -qi '^www-authenticate: *basic' <<<"$headers"; then
    echo "$status gate"
  else
    echo "$status passed"
  fi
}

expect() {
  local description="$1" method="$2" path="$3" auth="$4" wanted="$5" got
  got="$(probe "$method" "$path" "$auth")"
  # $wanted is a pattern, e.g. "@(401|503) passed"
  # shellcheck disable=SC2053
  if [[ "$got" == $wanted ]]; then
    echo "ok    $description: $got"
  else
    echo "FAIL  $description: got '$got', wanted '$wanted'"
    failures=$((failures + 1))
  fi
}

echo "Without a login: pages and API are behind the gate"
expect "web page" GET / no-login "401 gate"
expect "demo control page" GET /demo/control no-login "401 gate"
expect "LINE simulator page" GET /demo/line-sim no-login "401 gate"
expect "API health" GET /api/health no-login "401 gate"
expect "API docs" GET /api/docs no-login "401 gate"
expect "API clock" GET /api/clock no-login "401 gate"
expect "demo reset" POST /api/demo/reset no-login "401 gate"
expect "demo clock advance" POST /api/demo/clock/advance no-login "401 gate"
expect "demo clock freeze" POST /api/demo/clock/freeze no-login "401 gate"
expect "demo clock unfreeze" POST /api/demo/clock/unfreeze no-login "401 gate"
expect "demo check-in" POST /api/demo/attendance/check-in no-login "401 gate"

echo "Without a login: the webhook is the only exception, and only the exact request"
# The webhook passes the gate; the backend refuses the missing signature
# (401, or 503 while LINE_MODE is not real)
expect "LINE webhook" POST /api/line/webhook no-login "@(401|503) passed"
expect "webhook with GET" GET /api/line/webhook no-login "401 gate"
expect "path under the webhook" POST /api/line/webhook/x no-login "401 gate"
expect "webhook with a suffix" POST /api/line/webhooks no-login "401 gate"
expect "webhook with a trailing slash" POST /api/line/webhook/ no-login "401 gate"
expect "webhook with a query" POST "/api/line/webhook?x=1" no-login "401 gate"
expect "webhook path without /api" POST /line/webhook no-login "401 gate"
expect "webhook in upper case" POST /API/line/webhook no-login "401 gate"
expect "webhook with a changed case" POST /api/LINE/webhook no-login "401 gate"
expect "webhook with a double slash" POST /api//line/webhook no-login "401 gate"
expect "webhook with an encoded letter" POST /api/%6Cine/webhook no-login "401 gate"
expect "webhook with an encoded slash" POST /api/line/webhook%2F no-login "401 gate"
expect "webhook with a dot segment" POST /api/line/webhook/../health no-login "401 gate"

echo "Without a login: the internal routes are not reachable at all"
expect "internal route" POST /api/internal/merge-windows/close-due no-login "404 passed"
expect "internal route in upper case" POST /api/INTERNAL/merge-windows/close-due no-login "404 passed"

echo "With the login: the demo works"
expect "web page" GET / with-login "200 passed"
expect "demo control page" GET /demo/control with-login "200 passed"
expect "API health" GET /api/health with-login "200 passed"
expect "API clock" GET /api/clock with-login "200 passed"
expect "internal route (exists in the backend)" POST /api/internal/merge-windows/close-due with-login "404 passed"
expect "wrong password" GET /api/health wrong-login "401 gate"

if [ "$failures" -ne 0 ]; then
  echo "$failures check(s) failed"
  exit 1
fi
echo "All checks passed"
