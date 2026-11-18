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
    export ZABBIX_API_KEY=***   # env only - never pass secrets as CLI args
    python3 scripts/install_dashboard.py --host "your-ngaf-host-technical-name"

Caveats:
  * Credentials come from the environment ONLY: argv is visible in `ps`,
    shell history and container inspection.
  * Standalone dashboards import as PRIVATE to the API user. To let other
    users see it, share it in the UI (or grant a user group) afterwards.
  * Idempotency matches by dashboard NAME: if you rename the dashboard in
    the UI, re-running this script creates a second dashboard - delete the
    stale one manually.
  * Re-run this script after every template upgrade that changes items or
    graphs referenced by widgets.
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_FILE = os.path.join(HERE, os.pardir, "template_sangfor_ngaf_snmp.json")


from zabbix_api import api_call  # shared client (review #6)


def main():
    ap = argparse.ArgumentParser(
        description="Install the Sangfor NGAF dashboard (see module "
                    "docstring; ZABBIX_URL and ZABBIX_API_KEY come from "
                    "the environment).")
    ap.add_argument("--host", required=True,
                    help="technical name of the NGAF host the dashboard "
                         "should reference (items/graphs resolved per-host)")
    ap.add_argument("--template", default="Sangfor NGAF by SNMP")
    ap.add_argument("--url", default=os.environ.get("ZABBIX_URL"))
    args = ap.parse_args()
    token = os.environ.get("ZABBIX_API_KEY")
    if not args.url or not token:
        sys.exit("set ZABBIX_URL and ZABBIX_API_KEY in the environment "
                 "(--url accepted; the API key is intentionally NOT a CLI "
                 "argument)")

    with open(TEMPLATE_FILE, encoding="utf-8") as fh:
        doc = json.load(fh)["zabbix_export"]
    tpl = doc["templates"][0]
    dashboards = tpl.get("dashboards")
    if not dashboards:
        sys.exit("template JSON has no dashboards block")

    # host must exist and actually carry the template items
    hosts = api_call(args.url, token, "host.get",
                     {"output": ["hostid", "host"],
                      "filter": {"host": args.host}})
    if not hosts:
        sys.exit("host not found: %s" % args.host)
    hostid = hosts[0]["hostid"]
    n_items = len(api_call(args.url, token, "item.get",
                    {"hostids": [hostid], "output": ["itemid"],
                     "filter": {"key_": ["sangfor.device.name",
                                         "sangfor.cpu.util.1m",
                                         "sangfor.mem.util"]}}))
    if n_items < 3:
        sys.exit("host %s does not have the Sangfor template items "
                 "linked - import the template and link it first"
                 % args.host)
    linked = api_call(args.url, token, "host.get",
                      {"hostids": [hostid], "output": ["hostid"],
                       "selectParentTemplates": ["templateid", "host"]})
    tnames = [x["host"] for x in linked[0].get("parentTemplates", [])]
    if args.template not in tnames:
        sys.exit("host %s is not linked to template %r (linked: %s)"
                 % (args.host, args.template, tnames or "none"))

    # rewrite template-name references to the real host; strip uuids
    # (standalone dashboard documents do not carry them in 8.0)
    out_dashboards = []
    for dd_in in dashboards:
        dd = {"name": dd_in["name"], "pages": []}
        if "auto_start" in dd_in:
            dd["auto_start"] = dd_in["auto_start"]
        for page in dd_in["pages"]:
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

    res = api_call(args.url, token, "configuration.import",
        {"format": "json",
         "source": json.dumps({"zabbix_export":
                     {"version": "8.0", "dashboards": out_dashboards}}),
         "rules": {"dashboards": {"createMissing": True,
                                  "updateExisting": True}}})
    print("dashboard import result:", res)

    # verify widget fields survived
    dbs = api_call(args.url, token, "dashboard.get",
                   {"output": ["dashboardid", "name", "private"],
                    "selectPages": ["widgets"],
                    "filter": {"name": dashboards[0]["name"]}})
    if not dbs:
        sys.exit("dashboard not found after import?!")
    widgets = [w for p in dbs[0]["pages"] for w in p["widgets"]]
    kept = sum(1 for w in widgets if w.get("fields"))
    print("dashboard %s (%s): %d widgets, %d with resolved fields, private=%s"
          % (dbs[0]["name"], dbs[0]["dashboardid"], len(widgets), kept,
             dbs[0]["private"]))
    if kept < len(widgets):
        print("WARNING: some widget fields did not resolve; check item/graph "
              "existence on host", args.host, file=sys.stderr)


if __name__ == "__main__":
    main()
