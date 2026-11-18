"""Shared minimal Zabbix JSON-RPC client for the helper scripts.

Credentials come from the environment (ZABBIX_URL / ZABBIX_API_KEY); never
from CLI arguments (argv is visible in ps / shell history). Retries transient
network errors; distinguishes invalid/expired tokens from other API errors.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request


def credentials():
    url = os.environ.get("ZABBIX_URL")
    token = os.environ.get("ZABBIX_API_KEY")
    if not url or not token:
        sys.exit("set ZABBIX_URL and ZABBIX_API_KEY in the environment "
                 "(the API key is intentionally NOT a CLI argument)")
    return url, token


def api_call(url, token, method, params, retries=3):
    payload = json.dumps({"jsonrpc": "2.0", "method": method,
                          "params": params, "id": 1}).encode()
    resp = None
    # only idempotent reads are retried: a timed-out write may already have
    # been applied server-side, and a blind retry would then fail on a
    # duplicate and abort a run halfway
    if not (method.endswith(".get") or method == "apiinfo.version"):
        retries = 1
    for attempt in range(retries):
        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/json-rpc",
            "Authorization": "Bearer " + token})
        try:
            resp = json.loads(urllib.request.urlopen(req, timeout=30)
                               .read().decode())
            break
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt == retries - 1:
                sys.exit("API call %s failed after %d attempts: %s"
                         % (method, retries, e))
            time.sleep(2 * (attempt + 1))
    if "error" in resp:
        msg = json.dumps(resp["error"])
        low = msg.lower()
        if ("not authorised" in low or "not authorized" in low
                or "session terminated" in low or "re-login" in low):
            sys.exit("API token invalid/expired (%s): check ZABBIX_API_KEY "
                     "in the environment" % method)
        sys.exit("API ERROR %s: %s" % (method, msg[:400]))
    return resp["result"]
