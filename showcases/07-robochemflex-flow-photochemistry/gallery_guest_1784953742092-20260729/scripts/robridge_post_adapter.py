#!/usr/bin/env python3
"""Operator-authorized Robridge POST adapter for RoboChemFlex campaign execution.

Usage: robridge_post_adapter.py POST /v1/runs < body.json
Sends required RoboFlex User-Agent and X-API-Key headers.
"""
import os, sys, json
from urllib.request import Request, urlopen
from urllib.error import HTTPError

if len(sys.argv) != 3 or sys.argv[1].upper() != "POST":
    print("usage: robridge_post_adapter.py POST /v1/path", file=sys.stderr)
    sys.exit(2)
path = sys.argv[2]
base = os.getenv("ROBOFLEX_BASE_URL", "").rstrip("/")
key = os.getenv("ROBOFLEX_API_KEY", "").strip()
if not base:
    print("ROBOFLEX_BASE_URL is not set", file=sys.stderr); sys.exit(2)
if not key:
    print("ROBOFLEX_API_KEY is not set", file=sys.stderr); sys.exit(2)
body_text = sys.stdin.read() or "{}"
# Validate JSON before sending, then compact for transport.
try:
    body = json.dumps(json.loads(body_text)).encode("utf-8")
except Exception as exc:
    print(f"invalid JSON body: {exc}", file=sys.stderr); sys.exit(2)
url = f"{base}/{path.lstrip('/')}"
headers = {
    "Accept": "application/json, text/plain",
    "Content-Type": "application/json",
    "User-Agent": "roboflex-agent-tools/0.1",
    "X-API-Key": key,
}
req = Request(url, data=body, headers=headers, method="POST")
try:
    with urlopen(req, timeout=120) as resp:
        sys.stdout.write(resp.read().decode("utf-8"))
except HTTPError as e:
    sys.stderr.write(e.read().decode("utf-8", errors="replace") or str(e))
    sys.exit(1)
