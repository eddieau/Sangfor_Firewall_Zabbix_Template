#!/usr/bin/env python3
"""Install the "Sangfor NGAF" dashboard onto an existing host.

Why this script exists: on Zabbix 8.0.0 the configuration.import API silently
DROPS template-nested dashboards in all three formats (JSON/XML/YAML) - the
block stays in template_sangfor_ngaf_snmp.json for forward compatibility,
but today it has to be applied as a STANDALONE dashboard document whose
item/graph references point at a real host (your NGAF host, which inherits
the template items and graphs).

Usage:
    export ZABBIX_URL=https://your-zabbix.example.com/api_jsonrpc.php
    export ZABBIX_API_KEY=***
    python3 scripts/install_dashboard.py --host "your-ngaf-host-technical-name"

Idempotent: re-running updates the same dashboard (updateExisting).
"""
import argparse, json, os, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_FILE = os.path.join(HERE, os.pardir, "template_sangfor_ngaf_snmp.json")


def api_call(url, token, method, params):
    payload = json.dumps({"jsonrpc": "2.0", "method": method,
                          "params": params, "id": 1}).encode()
    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json-rpc",
        "Authorization": "Bearer " + token})
    resp = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
    if "error" in resp:
        sys.exit("API ERROR %s: %s" % (method,
                 json.dumps(resp["error"])[:400]))
    return resp["result"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True,
                    help="technical name of the NGAF host the dashboard "
                         "should reference (items/graphs resolved per-host)")
    ap.add_argument("--template", default="Sangfor NGAF by SNMP")
    ap.add_argument("--url", default=os.environ.get("ZABBIX_URL"))
    ap.add_argument("--token", default=os.environ.get("ZABBIX_API_KEY"))
    args = ap.parse_args()
    if not args.url or not args.token:
        sys.exit("set ZABBIX_URL and ZABBIX_API_KEY (or use --url/--token)")

    doc = json.load(open(TEMPLATE_FILE))["zabbix_export"]
    tpl = doc["templates"][0]
    dashboards = tpl.get("dashboards")
    if not dashboards:
        sys.exit("template JSON has no dashboards block")

    # host must exist and actually carry the template items
    hosts = api_call(args.url, args.token, "host.get",
                     {"output": ["hostid", "host"],
                      "filter": {"host": args.host}})
    if not hosts:
        sys.exit("host not found: %s" % args.host)
    hostid = hosts[0]["hostid"]
    n_items = len(api_call(args.url, args.token, "item.get",
                    {"hostids": [hostid], "output": ["itemid"],
                     "filter": {"key_": ["sangfor.device.name",
                                         "sangfor.cpu.util.1m",
                                         "sangfor.mem.util"]}}))
    if n_items < 3:
        sys.exit("host %s does not have the Sangfor template items "
                 "linked - import the template and link it first"
                 % args.host)

    # rewrite template-name references to the real host; strip dashboard uuid
    out_dashboards = []
    for d in dashboards:
        dd = {"name": d["name"], "pages": []}
        if "auto_start" in d:
            dd["auto_start"] = d["auto_start"]
        for page in d["pages"]:
            widgets = []
            for w in page["widgets"]:
                ww = {k: v for k, v in w.items() if k != "uuid"}
                fields = []
                for f in ww.get("fields", []):
                    ff = dict(f)
                    if isinstance(ff.get("value"), dict) and \
                            ff["value"].get("host") == args.template:
                        ff["value"] = dict(ff["value"], host=args.host)
                    fields.append(ff)
                if "fields" in ww:
                    ww["fields"] = fields
                widgets.append(ww)
            dd["pages"].append({"widgets": widgets})
        out_dashboards.append(dd)

    res = api_call(args.url, args.token, "configuration.import",
        {"format": "json",
         "source": json.dumps({"zabbix_export":
                     {"version": "8.0", "dashboards": out_dashboards}}),
         "rules": {"dashboards": {"createMissing": True,
                                  "updateExisting": True}}})
    print("dashboard import result:", res)

    # verify widget fields survived
    dbs = api_call(args.url, args.token, "dashboard.get",
                   {"output": ["dashboardid", "name"],
                    "selectPages": ["widgets"],
                    "filter": {"name": dashboards[0]["name"]}})
    if not dbs:
        sys.exit("dashboard not found after import?!")
    widgets = [w for p in dbs[0]["pages"] for w in p["widgets"]]
    kept = sum(1 for w in widgets if w.get("fields"))
    print("dashboard %s (%s): %d widgets, %d with resolved fields"
          % (dbs[0]["name"], dbs[0]["dashboardid"], len(widgets), kept))
    if kept < len(widgets):
        print("WARNING: some widget fields did not resolve; check item/graph "
              "existence on host", args.host, file=sys.stderr)


if __name__ == "__main__":
    main()
