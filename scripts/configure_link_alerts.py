#!/usr/bin/env python3
"""Auto-configure per-interface link-down alerting for Sangfor NGAF hosts.

Different sites wire different ports (eth0 vs eth9/eth10...). The template's
link-down trigger is opt-in per port via {$SANGFOR.IF.LINK.ALERT:"<ifname>"};
this helper sets those macros from each host's LIVE interface state:

  - physical port currently UP (oper=1, admin=1)   -> macro = 1 (in use)
  - physical port currently DOWN or admin-disabled -> macro removed (silent)
  - virtual interfaces (vpntun/ssltun*/veth*/lo/tun/tap) -> macro removed
    (VPN tunnels flap with sessions; not physical link faults)

A port that is down NOW but is known-critical will not be auto-enabled:
enable it manually after fixing/confirming, or re-run this helper once it is
up. Re-run after any re-cabling.

Usage (credentials from environment, never CLI):
    export ZABBIX_URL=https://zabbix.example.com/api_jsonrpc.php
    export ZABBIX_API_KEY=...
    python3 scripts/configure_link_alerts.py --host WSG-WFFW02-WH          # dry-run
    python3 scripts/configure_link_alerts.py --all --apply                 # all linked hosts
    python3 scripts/configure_link_alerts.py --host X --exclude-regex '^(vpntun|ssltun|veth|tun|tap|lo$)' --apply
"""
import argparse, json, os, re, sys, time, urllib.error, urllib.request

DEFAULT_EXCLUDE = r"^(vpntun|ssltun|veth|tun|tap|lo$)"
MACRO_FMT = '{$SANGFOR.IF.LINK.ALERT:"%s"}'


def api(url, token, method, params):
    payload = json.dumps({"jsonrpc": "2.0", "method": method,
                          "params": params, "id": 1}).encode()
    for attempt in range(3):
        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/json-rpc",
            "Authorization": "Bearer " + token})
        try:
            resp = json.loads(urllib.request.urlopen(req, timeout=30)
                               .read().decode())
            break
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt == 2:
                sys.exit("API %s failed: %s" % (method, e))
            time.sleep(2 * (attempt + 1))
    if "error" in resp:
        sys.exit("API ERROR %s: %s" % (method,
                 json.dumps(resp["error"])[:300]))
    return resp["result"]


def ifname_from_item(item_name):
    m = re.match(r"^Interface (.+): Operational status$", item_name)
    return m.group(1) if m else None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--host", action="append", default=[],
                    help="host technical or visible name (repeatable)")
    ap.add_argument("--all", action="store_true",
                    help="all hosts linked to the Sangfor template")
    ap.add_argument("--template", default="Sangfor NGAF by SNMP")
    ap.add_argument("--exclude-regex", default=DEFAULT_EXCLUDE,
                    help="virtual-interface name regex to keep silent")
    ap.add_argument("--apply", action="store_true",
                    help="apply changes (default: dry-run)")
    ap.add_argument("--url", default=os.environ.get("ZABBIX_URL"))
    args = ap.parse_args()
    token = os.environ.get("ZABBIX_API_KEY")
    if not args.url or not token:
        sys.exit("set ZABBIX_URL and ZABBIX_API_KEY in the environment")
    if not args.host and not args.all:
        sys.exit("give --host NAME (repeatable) or --all")

    tpl = api(args.url, token, "template.get",
              {"output": ["templateid"], "filter": {"host": args.template}})
    if not tpl:
        sys.exit("template not found: %s" % args.template)
    tid = tpl[0]["templateid"]

    if args.all:
        hosts = api(args.url, token, "host.get",
                    {"output": ["hostid", "host", "name"],
                     "templateids": [tid]})
    else:
        hosts = []
        for hname in args.host:
            found = api(args.url, token, "host.get",
                        {"output": ["hostid", "host", "name"],
                         "filter": {"host": hname}})
            if not found:
                found = api(args.url, token, "host.get",
                            {"output": ["hostid", "host", "name"],
                             "filter": {"name": hname}})
            if not found:
                sys.exit("host not found: %s" % hname)
            hosts.extend(found)

    excl = re.compile(args.exclude_regex)
    total_changes = 0
    for h in hosts:
        hid = h["hostid"]
        items = api(args.url, token, "item.get",
                    {"hostids": [hid], "output": ["name", "key_", "lastvalue"],
                     "search": {"key_": "sangfor.if.operstatus"}})
        adm = api(args.url, token, "item.get",
                  {"hostids": [hid], "output": ["key_", "lastvalue"],
                   "search": {"key_": "sangfor.if.adminstatus"}})
        adm_by_idx = {i["key_"].split("[")[1].rstrip("]"): i["lastvalue"]
                      for i in adm}
        macros = api(args.url, token, "usermacro.get",
                     {"hostids": [hid], "output": ["hostmacroid", "macro", "value"]})
        link_macros = {}
        for m in macros:
            mm = re.match(r'^\{\$SANGFOR\.IF\.LINK\.ALERT:"(.+)"\}$', m["macro"])
            if mm:
                link_macros[mm.group(1)] = m

        print("\n=== %s (%s) ===" % (h["name"] or h["host"], hid))
        print("%-10s %-5s %-6s %-8s %s" % ("iface", "oper", "admin", "macro", "action"))
        seen = set()
        for it in sorted(items, key=lambda x: x["name"]):
            name = ifname_from_item(it["name"])
            if not name:
                continue
            seen.add(name)
            idx = it["key_"].split("[")[1].rstrip("]")
            oper = it.get("lastvalue", "")
            admin = adm_by_idx.get(idx, "")
            virtual = bool(excl.search(name))
            want_on = (oper == "1" and admin == "1" and not virtual)
            cur = link_macros.get(name)
            cur_on = cur is not None and cur["value"] == "1"
            if want_on and not cur_on:
                action = "ENABLE"
                if args.apply:
                    if cur:
                        api(args.url, token, "usermacro.update",
                            {"hostmacroid": cur["hostmacroid"], "value": "1"})
                    else:
                        api(args.url, token, "usermacro.create",
                            {"hostid": hid, "macro": MACRO_FMT % name,
                             "value": "1"})
                total_changes += 1
            elif not want_on and cur is not None:
                action = "remove (idle/down/virtual)"
                if args.apply:
                    api(args.url, token, "usermacro.delete", [cur["hostmacroid"]])
                total_changes += 1
            else:
                action = "-"
            print("%-10s %-5s %-6s %-8s %s" % (
                name, oper or "?", admin or "?",
                (cur["value"] if cur else "-"), action))
        # macros for interfaces that no longer exist
        for name, m in link_macros.items():
            if name not in seen:
                print("%-10s %-5s %-6s %-8s %s" % (name, "-", "-",
                      m["value"], "remove (interface gone)"))
                if args.apply:
                    api(args.url, token, "usermacro.delete", [m["hostmacroid"]])
                total_changes += 1
    print("\n%s: %d change(s)%s" % (
        "APPLIED" if args.apply else "DRY-RUN", total_changes,
        "" if args.apply else " (re-run with --apply to commit)"))


if __name__ == "__main__":
    main()
