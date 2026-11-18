#!/usr/bin/env python3
"""CI live-import test: import the template into a REAL Zabbix 8.0 and
assert the live object counts match the shipped JSON.

Why: static checks cannot catch import-time failures. Three releases of
trigger changes once silently never applied (one bad expression made the
import skip the whole trigger batch while returning true). This test
imports into a throwaway stack (ci/docker-compose.yml) and verifies with
trigger.get / triggerprototype.get - NOT configuration.export, which
under-reports trigger prototypes on some builds.

Env: ZABBIX_CI_URL (default http://localhost:8080/api_jsonrpc.php)
Login: fresh-stack default Admin/zabbix (CI only).
"""
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_FILE = os.path.join(HERE, os.pardir, "template_sangfor_ngaf_snmp.json")
URL = os.environ.get("ZABBIX_CI_URL", "http://localhost:8080/api_jsonrpc.php")

_token = None


def call(method, params, auth=True):
    headers = {"Content-Type": "application/json-rpc"}
    if auth and _token:
        headers["Authorization"] = "Bearer " + _token
    payload = json.dumps({"jsonrpc": "2.0", "method": method,
                          "params": params, "id": 1}).encode()
    req = urllib.request.Request(URL, data=payload, headers=headers)
    resp = json.loads(urllib.request.urlopen(req, timeout=60).read().decode())
    if "error" in resp:
        raise RuntimeError("%s: %s" % (method, json.dumps(resp["error"])[:300]))
    return resp["result"]


def wait_ready(timeout=600):
    global _token
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            call("apiinfo.version", {}, auth=False)
            _token = call("user.login",
                          {"username": "Admin", "password": "zabbix"},
                          auth=False)
            return
        except Exception:
            time.sleep(5)
    sys.exit("Zabbix API never became ready at %s" % URL)


def main():
    with open(TEMPLATE_FILE, encoding="utf-8") as fh:
        doc = json.load(fh)
    t = doc["zabbix_export"]["templates"][0]
    exp_items = len(t["items"])
    exp_trigs = sum(len(i.get("triggers", [])) for i in t["items"])
    exp_protos = sum(len(dr.get("trigger_prototypes", []))
                     for dr in t["discovery_rules"])
    exp_iprotos = sum(len(dr.get("item_prototypes", []))
                      for dr in t["discovery_rules"])
    exp_macros = len(t.get("macros", []))
    exp_lld = len(t["discovery_rules"])
    print("expected: items=%d triggers=%d trig_protos=%d item_protos=%d "
          "macros=%d lld=%d" % (exp_items, exp_trigs, exp_protos,
                                exp_iprotos, exp_macros, exp_lld))

    wait_ready()
    rules = {
        "templates": {"createMissing": True, "updateExisting": True},
        "host_groups": {"createMissing": True},
        "items": {"createMissing": True, "updateExisting": True,
                  "deleteMissing": True},
        "discoveryRules": {"createMissing": True, "updateExisting": True,
                           "deleteMissing": True},
        "triggers": {"createMissing": True, "updateExisting": True,
                     "deleteMissing": True},
        "graphs": {"createMissing": True, "updateExisting": True},
        "valueMaps": {"createMissing": True, "updateExisting": True},
        "dashboards": {"createMissing": True, "updateExisting": True},
    }
    src = json.dumps(doc)

    # upgrade path: import the PREVIOUS release first (CI passes it via
    # PREV_TEMPLATE), then the current file over it. Proves in-place update
    # (stable UUIDs) instead of duplicate objects.
    prev_path = os.environ.get("PREV_TEMPLATE")
    if prev_path and os.path.exists(prev_path):
        with open(prev_path, encoding="utf-8") as fh:
            prev_src = fh.read()
        if prev_src.strip() and json.loads(prev_src) != doc:
            print("upgrade test: importing previous release first")
            for attempt in (1, 2):
                try:
                    call("configuration.import", {"format": "json",
                         "source": prev_src, "rules": rules})
                    break
                except RuntimeError as e:
                    if attempt == 2:
                        raise
                    print("prev import pass 1 failed (%s) - retrying" % str(e)[:120])
        else:
            print("upgrade test: previous release identical or empty - skipped")
    # Two-pass tolerance: on an empty DB the first pass can fail resolving
    # bare-name trigger dependencies; the identical second pass succeeds.
    try:
        call("configuration.import",
             {"format": "json", "source": src, "rules": rules})
        print("import pass 1: OK")
    except RuntimeError as e:
        print("import pass 1 failed (%s) - retrying identical import" % str(e)[:120])
        call("configuration.import",
             {"format": "json", "source": src, "rules": rules})
        print("import pass 2: OK")
    # idempotence: a third identical import must also succeed
    call("configuration.import",
         {"format": "json", "source": src, "rules": rules})
    print("import pass 3 (idempotence): OK")

    tid = call("template.get", {"output": ["templateid"],
                                "filter": {"host": t["template"]}})[0]["templateid"]
    live = {
        "items": len(call("item.get", {"hostids": [tid], "output": ["itemid"]})),
        "triggers": len(call("trigger.get", {"hostids": [tid],
                                             "output": ["triggerid"]})),
        "trig_protos": len(call("triggerprototype.get",
                                {"hostids": [tid], "output": ["triggerid"]})),
        "macros": len(call("usermacro.get", {"hostids": [tid],
                                             "output": ["hostmacroid"]})),
        "lld": len(call("discoveryrule.get", {"hostids": [tid],
                                              "output": ["itemid"]})),
    }
    # item prototypes: use the authoritative itemprototype.get. The
    # discoveryrule.get selectItemPrototypes sub-select returns an empty
    # list on some builds (false 0), same class of bug as export
    # under-reporting trigger prototypes. Verified live: 21 == JSON.
    live["item_protos"] = len(call("itemprototype.get",
                                   {"hostids": [tid], "output": ["itemid"]}))
    # --- object classes the count checks above do not cover
    exp_graphs = len(doc["zabbix_export"].get("graphs", []))
    exp_gprotos = sum(len(dr.get("graph_prototypes", []))
                      for dr in t["discovery_rules"])
    exp_vm = len(t.get("valuemaps", []))
    live["graphs"] = len(call("graph.get", {"hostids": [tid],
                                            "output": ["graphid"]}))
    live["graph_protos"] = len(call("graphprototype.get", {"hostids": [tid],
                                                           "output": ["graphid"]}))
    live["valuemaps"] = len(call("valuemap.get", {"hostids": [tid],
                                                  "output": ["valuemapid"]}))
    # every trigger and trigger prototype must carry a scope tag
    tr_all = call("trigger.get", {"hostids": [tid], "output": ["triggerid"],
                                  "selectTags": ["tag"]})
    tp_all = call("triggerprototype.get", {"hostids": [tid],
                                           "output": ["triggerid"],
                                           "selectTags": ["tag"]})
    live["scope_tagged"] = sum(1 for x in tr_all + tp_all
                               if any(g["tag"] == "scope" for g in x["tags"]))
    exp_scope = exp_trigs + exp_protos
    # LLD filter + override survived import (silently dropped otherwise)
    rules_live = call("discoveryrule.get", {
        "hostids": [tid], "output": ["key_"],
        "selectFilter": "extend", "selectOverrides": "extend"})
    by_key = {r["key_"]: r for r in rules_live}
    exp_dr = {d["key"]: d for d in t["discovery_rules"]}
    live["if_filter_conditions"] = len(
        by_key["sangfor.if.discovery"]["filter"].get("conditions", []))
    live["if_overrides"] = len(by_key["sangfor.if.discovery"].get("overrides", []))
    exp_if_cond = len(exp_dr["sangfor.if.discovery"]["filter"].get("conditions", []))
    exp_if_ovr = len(exp_dr["sangfor.if.discovery"].get("overrides", []))
    expected = {"graphs": exp_graphs, "graph_protos": exp_gprotos,
                "valuemaps": exp_vm, "scope_tagged": exp_scope,
                "if_filter_conditions": exp_if_cond,
                "if_overrides": exp_if_ovr}
    expected.update({"items": exp_items, "triggers": exp_trigs,
                "trig_protos": exp_protos, "item_protos": exp_iprotos,
                "macros": exp_macros, "lld": exp_lld})
    fails = []
    for k, want in expected.items():
        got = live[k]
        status = "OK" if got == want else "MISMATCH"
        print("  %-12s live=%-4d expected=%-4d %s" % (k, got, want, status))
        if got != want:
            fails.append(k)
    # vendor block acceptance
    exp = call("configuration.export",
               {"format": "json", "options": {"templates": [tid]}})
    vendor = json.loads(exp)["zabbix_export"]["templates"][0].get("vendor")
    print("  vendor block:", vendor)
    if not vendor or vendor.get("version") != t.get("vendor", {}).get("version"):
        fails.append("vendor")
    if fails:
        sys.exit("LIVE-IMPORT TEST FAILED: %s" % fails)
    print("LIVE-IMPORT TEST PASSED")


if __name__ == "__main__":
    main()
