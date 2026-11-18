#!/usr/bin/env python3
"""Auto-configure per-interface link-down alerting for Sangfor NGAF hosts.

Different sites wire different ports (eth0 vs eth9/eth10...). The template's
link-down trigger is opt-in per port via {$SANGFOR.IF.LINK.ALERT:"<ifname>"};
this helper ENABLES those macros from each host's live interface state.

SAFETY SEMANTICS (review #6 - never silence a fault by accident):
  - physical port currently UP (oper=1, admin=1)  -> enable macro (=1)
  - port DOWN / idle / unknown value              -> macro PRESERVED as-is
    (a critical WAN line that is down during a run must keep its alerting;
    a device that is unreachable yields no values -> port is skipped)
  - removal of macros happens ONLY with --prune, and ONLY for virtual
    interfaces ({$SANGFOR.IF.VIRTUAL.MATCHES}) or interfaces that no longer
    exist on the host. Without --prune nothing is ever deleted.

Alternative to per-port macros (verified on Zabbix 8.0): a single host
macro with a REGEX CONTEXT DEFINITION covers many ports at once, e.g.
{$SANGFOR.IF.LINK.ALERT:regex:"^(eth9|eth10)$"} = 1. The template's usage
site {$SANGFOR.IF.LINK.ALERT:"{#SNMPVALUE}"} resolves against it. (Regex at
the usage site does NOT work; regex belongs in the macro definition.)

Usage (credentials from environment, never CLI):
    export ZABBIX_URL=https://zabbix.example.com/api_jsonrpc.php
    export ZABBIX_API_KEY=...
    python3 scripts/configure_link_alerts.py --all             # dry-run
    python3 scripts/configure_link_alerts.py --all --apply     # enable in-use ports
    python3 scripts/configure_link_alerts.py --all --apply --prune  # also clean virtual/gone
"""
import argparse
import re
import sys

from zabbix_api import api_call, credentials

MACRO_FMT = '{$SANGFOR.IF.LINK.ALERT:"%s"}'
VIRTUAL_MACRO = "{$SANGFOR.IF.VIRTUAL.MATCHES}"
DEFAULT_VIRTUAL = r"^(vpntun|ssltun|veth|tun|tap|lo$)"


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
    ap.add_argument("--exclude-regex", default=None,
                    help="override the virtual-interface regex (default: "
                         "read %s from the template)" % VIRTUAL_MACRO)
    ap.add_argument("--prune", action="store_true",
                    help="also REMOVE macros for virtual interfaces and "
                         "interfaces that no longer exist (never removes "
                         "macros of real ports that are merely down)")
    ap.add_argument("--apply", action="store_true",
                    help="apply changes (default: dry-run)")
    ap.add_argument("--url", default=None)
    args = ap.parse_args()
    env_url, token = credentials()
    url = args.url or env_url
    if not args.host and not args.all:
        sys.exit("give --host NAME (repeatable) or --all")

    tpl = api_call(url, token, "template.get",
                   {"output": ["templateid"], "filter": {"host": args.template}})
    if not tpl:
        sys.exit("template not found: %s" % args.template)
    tid = tpl[0]["templateid"]

    # single source of truth for the virtual-interface regex
    virtual_re = args.exclude_regex
    if not virtual_re:
        tm = api_call(url, token, "usermacro.get",
                      {"hostids": [tid], "output": ["macro", "value"],
                       "filter": {"macro": [VIRTUAL_MACRO]}})
        virtual_re = tm[0]["value"] if tm else DEFAULT_VIRTUAL
    excl = re.compile(virtual_re)
    print("virtual-interface regex: %s" % virtual_re)

    if args.all:
        hosts = api_call(url, token, "host.get",
                         {"output": ["hostid", "host", "name"],
                          "templateids": [tid]})
    else:
        hosts = []
        for hname in args.host:
            found = api_call(url, token, "host.get",
                             {"output": ["hostid", "host", "name"],
                              "filter": {"host": hname}})
            if not found:
                found = api_call(url, token, "host.get",
                                 {"output": ["hostid", "host", "name"],
                                  "filter": {"name": hname}})
            if not found:
                sys.exit("host not found: %s" % hname)
            hosts.extend(found)

    total_changes = 0
    for h in hosts:
        hid = h["hostid"]
        items = api_call(url, token, "item.get",
                         {"hostids": [hid], "output": ["name", "key_", "lastvalue"],
                          "search": {"key_": "sangfor.if.operstatus"}})
        adm = api_call(url, token, "item.get",
                       {"hostids": [hid], "output": ["key_", "lastvalue"],
                        "search": {"key_": "sangfor.if.adminstatus"}})
        adm_by_idx = {i["key_"].split("[")[1].rstrip("]"): i["lastvalue"]
                      for i in adm}
        macros = api_call(url, token, "usermacro.get",
                          {"hostids": [hid],
                           "output": ["hostmacroid", "macro", "value"]})
        link_macros = {}
        for m in macros:
            mm = re.match(r'^\{\$SANGFOR\.IF\.LINK\.ALERT:"(.+)"\}$', m["macro"])
            if mm:
                link_macros[mm.group(1)] = m

        print("\n=== %s (%s) ===" % (h["name"] or h["host"], hid))
        print("%-10s %-5s %-6s %-6s %s" % ("iface", "oper", "admin", "macro", "action"))
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
            cur = link_macros.get(name)
            cur_on = cur is not None and cur["value"] == "1"

            if oper == "" or admin == "":
                action = "SKIP (no data - device unreachable?)"
            elif oper == "1" and admin == "1" and not virtual:
                if cur_on:
                    action = "-"
                else:
                    action = "ENABLE"
                    if args.apply:
                        if cur:
                            api_call(url, token, "usermacro.update",
                                     {"hostmacroid": cur["hostmacroid"],
                                      "value": "1"})
                        else:
                            api_call(url, token, "usermacro.create",
                                     {"hostid": hid, "macro": MACRO_FMT % name,
                                      "value": "1"})
                    total_changes += 1
            elif virtual and cur is not None:
                if args.prune:
                    action = "remove (virtual, --prune)"
                    if args.apply:
                        api_call(url, token, "usermacro.delete",
                                 [cur["hostmacroid"]])
                    total_changes += 1
                else:
                    action = "keep (virtual; use --prune to remove)"
            else:
                # down / admin-disabled / idle real port: NEVER touch the
                # macro - it may be a manually-enabled critical line that
                # is down right now (review #6 bug fix).
                action = "keep (down/idle - macro preserved)" if cur else "-"
            print("%-10s %-5s %-6s %-6s %s" % (
                name, oper or "?", admin or "?",
                (cur["value"] if cur else "-"), action))

        for name, m in link_macros.items():
            if name not in seen:
                if args.prune:
                    print("%-10s %-5s %-6s %-6s %s" % (name, "-", "-",
                          m["value"], "remove (interface gone, --prune)"))
                    if args.apply:
                        api_call(url, token, "usermacro.delete",
                                 [m["hostmacroid"]])
                    total_changes += 1
                else:
                    print("%-10s %-5s %-6s %-6s %s" % (name, "-", "-",
                          m["value"], "keep (interface gone; --prune to remove)"))
    print("\n%s: %d change(s)%s" % (
        "APPLIED" if args.apply else "DRY-RUN", total_changes,
        "" if args.apply else " (re-run with --apply to commit)"))


if __name__ == "__main__":
    main()
