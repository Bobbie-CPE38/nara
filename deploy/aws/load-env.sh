#!/usr/bin/env bash
# Writes the parameters under one Parameter Store path to an env file for
# docker compose (round 6 PR D, docs/deploy-aws.md). The app only reads env,
# so it never needs to know about Parameter Store (docs/workflow.md 6.16).
#
# Parameter /nara/test/LINE_CHANNEL_SECRET becomes LINE_CHANNEL_SECRET='...'.
# Values are single-quoted, so compose takes them as written: a "$" in the
# Basic Auth hash is not read as a variable.
#
# Settings (environment): NARA_PARAMETER_REGION (required: the Region of Parameter Store),
# NARA_PARAMETER_PATH (default /nara/test), NARA_ENV_FILE (default /etc/nara/nara.env).
# AWS_REGION is not read here. It is the Region the app calls Bedrock in and comes from
# the Parameter of that name. Compose takes a variable of the process environment over
# --env-file, so one name for both would replace the Bedrock Region silently.
# Credentials come from the instance's IAM Role.

set -euo pipefail

region="${NARA_PARAMETER_REGION:-}"
if [ -z "$region" ]; then
  if [ -n "${AWS_REGION:-}" ]; then
    echo "AWS_REGION is the Bedrock Region of the app. Name the Parameter Store Region NARA_PARAMETER_REGION in /etc/nara/aws.conf." >&2
  fi
  echo "Set NARA_PARAMETER_REGION, e.g. in /etc/nara/aws.conf" >&2
  exit 1
fi
parameter_path="${NARA_PARAMETER_PATH:-/nara/test}"
env_file="${NARA_ENV_FILE:-/etc/nara/nara.env}"
required=(SITE_DOMAIN ACME_EMAIL BASIC_AUTH_USER BASIC_AUTH_HASH POSTGRES_PASSWORD INTERNAL_JOB_SECRET)

mkdir -p "$(dirname "$env_file")"
tmp="$(mktemp "${env_file}.XXXXXX")"
trap 'rm -f "$tmp"' EXIT
chmod 600 "$tmp"

# The AWS CLI follows every page of the result itself
aws ssm get-parameters-by-path \
  --region "$region" \
  --path "$parameter_path" \
  --with-decryption \
  --output json |
  python3 -c '
import json
import re
import sys

required = sys.argv[1].split()
written = set()
for parameter in json.load(sys.stdin)["Parameters"]:
    name = parameter["Name"].rsplit("/", 1)[-1]
    value = parameter["Value"]
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
        sys.exit(f"Parameter name {name!r} is not an env variable name")
    if "\x27" in value or "\n" in value:
        sys.exit(f"Parameter {name} has a quote or a line break, which the env file cannot hold")
    print(f"{name}=\x27{value}\x27")
    written.add(name)
missing = [name for name in required if name not in written]
if missing:
    sys.exit("Missing parameters: " + ", ".join(missing))
' "${required[*]}" >"$tmp"

mv "$tmp" "$env_file"
trap - EXIT
echo "Wrote $(wc -l <"$env_file") parameters from $parameter_path to $env_file"
