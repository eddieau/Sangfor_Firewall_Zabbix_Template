#!/usr/bin/env python3
"""Integrity checks for template_sangfor_ngaf_snmp.json.

Run locally (`python3 scripts/check_template.py`) - CI runs the same file.
Exit code 0 = all good.
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DOC = os.path.join(HERE, os.pardir, "template_sangfor_ngaf_snmp.json")
TPL = "Sangfor NGAF by SNMP"

errors = []

def check(cond, msg):
    if not cond:
        errors.append(msg)


def parse_refs(expr):
    """Extract item keys referenced as /Template/KEY inside a trigger
    expression (bracket-depth aware; keys contain commas and pipes inside
    [ ])."""
    refs = []
    marker = "/" + TPL + "/"
    i = 0
    while True:
        j = expr.find(marker, i)
        if j < 0:
            break
        k = j + len(marker)
        start = k
        depth = 0
        while k < len(expr):
            c = expr[k]
            if c in "([{":
                depth += 1
            elif c in ")]}":
                if depth == 0:
                    break
                depth -= 1
            elif c in ",)" and depth == 0:
                break
            k += 1
        refs.append(expr[start:k])
        i = k
    return refs


def collect_uuids(x, found, collisions, path=""):
    if isinstance(x, dict):
        u = x.get("uuid")
        if isinstance(u, str):
            if u in found:
                collisions.append((u, found[u], path))
            else:
                found[u] = path
        for k2, v in x.items():
            collect_uuids(v, found, collisions,
                          f"{path}.{k2}" if path else k2)
    elif isinstance(x, list):
        for i, v in enumerate(x):
            collect_uuids(v, found, collisions, f"{path}[{i}]")


def main():
    d = json.load(open(DOC))["zabbix_export"]
    t = d["templates"][0]
    graphs = d.get("graphs", [])
    check(t["template"] == TPL, "template name mismatch")
    check(len(t["items"]) >= 50, "too few items: %d" % len(t["items"]))
    check(len(t["discovery_rules"]) == 6, "LLD count != 6")
    check(len(graphs) >= 4, "fewer than 4 template graphs")
    check(t.get("dashboards"), "dashboards block missing")

    item_keys = {i["key"] for i in t["items"]}
    check(len(item_keys) == len(t["items"]), "duplicate item keys")
    check("snmptrap.fallback" in item_keys, "fallback trap item missing")
    check("icmpping" in item_keys, "ported ICMP missing")

    proto_keys = set()
    for dr in t["discovery_rules"]:
        proto_keys |= {p["key"] for p in dr.get("item_prototypes", [])}

    # ---- uuid hygiene over the WHOLE document
    found, collisions = {}, []
    collect_uuids(d, found, collisions)
    check(not collisions, "duplicate uuids: %s" % (collisions[:3],))
    # UUIDv4 layout: version nibble "4" at hex pos 12, variant 8/9/a/b at pos 16
    v4 = re.compile(r"^[0-9a-f]{12}4[0-9a-f]{3}[89ab][0-9a-f]{15}$")
    bad = [u for u in found if not v4.match(u)]
    check(not bad, "non-UUIDv4 objects (version/variant nibble): %s"
          % (bad[:3],))

    # ---- macros: every {$X} (incl. context form {$X:"ctx"}) used must be
    #      defined in the template. Walk real string values (not the JSON
    #      dump) so escaped quotes in context macros are seen correctly.
    defined = {m["macro"] for m in t.get("macros", [])}
    strings = []
    def collect(x):
        if isinstance(x, dict):
            for v in x.values():
                collect(v)
        elif isinstance(x, list):
            for v in x:
                collect(v)
        elif isinstance(x, str):
            strings.append(x)
    collect(d)
    used = set()
    for s in strings:
        for m in re.findall(r"\{\$[A-Z0-9_.]+(?::\"[^\"]*\")?\}", s):
            used.add(m.split(":")[0] + "}" if ":" in m else m)
    undefined = used - defined
    check(not undefined, "macros used but not defined: %s" % sorted(undefined))

    # ---- trigger expressions reference existing keys
    def check_expr(exprs, where, known):
        for e in exprs:
            for ref in parse_refs(e):
                check(ref in known,
                      "%s references unknown key %r" % (where, ref))

    item_exprs = []
    for i in t["items"]:
        for tr in i.get("triggers", []):
            item_exprs.append(tr["expression"])
            item_exprs.append(tr.get("recovery_expression", ""))
            for dep in tr.get("dependencies", []):
                item_exprs.append(dep.get("expression", ""))
    check_expr([e for e in item_exprs if e], "item trigger", item_keys)

    for dr in t["discovery_rules"]:
        pexprs = []
        for tr in dr.get("trigger_prototypes", []):
            pexprs.append(tr["expression"])
            pexprs.append(tr.get("recovery_expression", ""))
        check_expr([e for e in pexprs if e],
                   "prototype trigger " + dr["key"], proto_keys)

    # ---- trigger name uniqueness (import resolves deps by bare name)
    names = [tr["name"] for i in t["items"] for tr in i.get("triggers", [])]
    names += [tr["name"] for dr in t["discovery_rules"]
              for tr in dr.get("trigger_prototypes", [])]
    check(len(names) == len(set(names)),
          "duplicate trigger names (bare-name dependency resolution is "
          "ambiguous): %s" % [n for n in names if names.count(n) > 1][:3])

    # every dependency name must exist among trigger names (import resolves
    # deps by bare name; a typo passes expression checks but fails import)
    nameset = set(names)
    for i in t["items"]:
        for tr in i.get("triggers", []):
            for dep in tr.get("dependencies", []):
                check(dep["name"] in nameset,
                      "trigger %r depends on unknown trigger name %r"
                      % (tr["name"], dep["name"]))

    # ---- find() regexp pattern literals must be BARE names (no
    #      backslashes): full anchored strings with \\ escapes inside the
    #      quoted pattern are silently rejected by some Zabbix 8.0 import
    #      parsers, which skips the ENTIRE trigger batch of the import.
    #      Routing precision comes from the anchored item KEY, not the
    #      find() pattern.
    _pat_trigs = [tr for i in t["items"] for tr in i.get("triggers", [])]
    _pat_trigs += [tr for dr in t["discovery_rules"]
                   for tr in dr.get("trigger_prototypes", [])]
    for tr in _pat_trigs:
        for pat in re.findall(r'"regexp","([^"]*)"', tr.get("expression", "")):
            check("\\" not in pat,
                  "trigger %r find() pattern contains backslashes "
                  "(silent import-batch skip risk): %r" % (tr["name"], pat[:60]))

    # ---- trap routing anchored: named trap keys must anchor on the
    #      snmpTrapOID varbind line (prevents payload false matches and
    #      double-routing, since a trap is copied to EVERY matching item)
    for i in t["items"]:
        if i["key"].startswith("snmptrap["):
            inner = i["key"][len("snmptrap["):-1]
            for alt in inner.split("|"):
                check(alt.startswith("snmpTrapOID"),
                      "trap key not anchored on snmpTrapOID line: %s"
                      % i["key"][:80])

    # ---- graph / graph-prototype item refs exist
    for g in graphs:
        for gi in g["graph_items"]:
            ref = gi["item"]
            check(ref["host"] == TPL,
                  "graph %s: foreign host %s" % (g["name"], ref["host"]))
            check(ref["key"] in item_keys,
                  "graph %s references unknown key %r" % (g["name"], ref["key"]))
    for dr in t["discovery_rules"]:
        for g in dr.get("graph_prototypes", []):
            for gi in g["graph_items"]:
                check(gi["item"]["host"] == TPL,
                      "graph prototype %s: foreign host %s"
                      % (g["name"], gi["item"]["host"]))
                check(gi["item"]["key"] in proto_keys,
                      "graph prototype %s references unknown prototype key %r"
                      % (g["name"], gi["item"]["key"]))

    # ---- dashboard: item/graph references exist; widget references unique
    graph_names = {g["name"] for g in graphs}
    refs_seen = []
    for db in t.get("dashboards", []):
        for p in db.get("pages", []):
            check(set(p.keys()) == {"widgets"},
                  "dashboard page has keys other than 'widgets' "
                  "(importer silently drops such dashboards)")
            for w in p.get("widgets", []):
                for fld in w.get("fields", []):
                    if fld["type"] == "ITEM":
                        v = fld["value"]
                        check(v["host"] == TPL and v["key"] in item_keys,
                              "dashboard widget %s references unknown item %r"
                              % (w["name"], v))
                    if fld["type"] == "GRAPH":
                        v = fld["value"]
                        check(v["host"] == TPL and v["name"] in graph_names,
                              "dashboard widget %s references unknown graph %r"
                              % (w["name"], v))
                    if fld["name"] == "reference":
                        refs_seen.append(fld["value"])
    check(len(refs_seen) == len(set(refs_seen)),
          "duplicate dashboard widget references: %s"
          % [r for r in refs_seen if refs_seen.count(r) > 1])

    # ---- valuemaps: every referenced valuemap is defined
    vmnames = {v["name"] for v in t.get("valuemaps", [])}
    for i in t["items"]:
        if "valuemap" in i:
            check(i["valuemap"]["name"] in vmnames,
                  "item %s references undefined valuemap %r"
                  % (i["key"], i["valuemap"]["name"]))
    for dr in t["discovery_rules"]:
        for p in dr.get("item_prototypes", []):
            if "valuemap" in p:
                check(p["valuemap"]["name"] in vmnames,
                      "prototype %s references undefined valuemap %r"
                      % (p["key"], p["valuemap"]["name"]))

    # ---- trigger quality: every trigger needs a scope tag + description
    all_trigs = [tr for i in t["items"] for tr in i.get("triggers", [])]
    all_trigs += [tr for dr in t["discovery_rules"]
                  for tr in dr.get("trigger_prototypes", [])]
    valid_scopes = {"availability", "performance", "capacity", "security",
                    "notice", "fault"}
    for tr in all_trigs:
        scopes = [x["value"] for x in tr.get("tags", [])
                  if x["tag"] == "scope"]
        check(bool(scopes) and scopes[0] in valid_scopes,
              "trigger %r missing/invalid scope tag" % tr["name"])
        check(bool(tr.get("description")),
              "trigger %r missing description" % tr["name"])

    # ---- hysteresis: recovery strictly below the problem threshold
    for tr in all_trigs:
        expr = tr.get("expression", "")
        rec = tr.get("recovery_expression", "")
        m = re.search(r">\{\$([A-Z0-9_.]+)\}", expr)
        if m and rec:
            macro = m.group(1)
            fm = re.search(r"<\{\$" + re.escape(macro) +
                           r"\}\*([0-9.]+)", rec)
            sm = re.search(r"<\{\$" + re.escape(macro) +
                           r"\}-([0-9.]+)", rec)
            if fm:
                check(float(fm.group(1)) < 1.0,
                      "trigger %r hysteresis factor not <1" % tr["name"])
            elif sm:
                check(float(sm.group(1)) > 0.0,
                      "trigger %r hysteresis offset not >0" % tr["name"])

    # ---- DISCARD_UNCHANGED_HEARTBEAT must never sit on trap/uptime/name
    #      items (breaks nodata()/change()/#1<>#2 trigger semantics)
    def _has_dch(it):
        return any(s.get("type") == "DISCARD_UNCHANGED_HEARTBEAT"
                   for s in it.get("preprocessing", []))
    for i in t["items"]:
        if _has_dch(i):
            k = i["key"]
            check(not (k.startswith("snmptrap") or "uptime" in k
                       or k == "system.name"),
                  "DISCARD_UNCHANGED_HEARTBEAT on forbidden item %s" % k)
    for dr in t["discovery_rules"]:
        for p in dr.get("item_prototypes", []):
            if _has_dch(p):
                check(not (p["key"].startswith("snmptrap")
                           or "uptime" in p["key"]),
                      "DISCARD_UNCHANGED_HEARTBEAT on forbidden proto %s"
                      % p["key"])

    # ---- README item count must match the JSON (drift is a real risk)
    readme_path = os.path.join(HERE, os.pardir, "README.md")
    if os.path.exists(readme_path):
        rd = open(readme_path, encoding="utf-8").read()
        cm = re.search(r"(\d+) template-level items", rd)
        if cm:
            check(int(cm.group(1)) == len(t["items"]),
                  "README says %s template-level items, JSON has %d"
                  % (cm.group(1), len(t["items"])))

    # ---- version coherence: generator VERSION == JSON vendor version ==
    #      newest CHANGELOG heading
    gen_src = open(os.path.join(HERE, "gen_template.py"), encoding="utf-8").read()
    vm = re.search(r'^VERSION = "([^"]+)"', gen_src, re.M)
    cl = os.path.join(HERE, os.pardir, "CHANGELOG.md")
    if vm:
        check(t.get("vendor", {}).get("version") == vm.group(1),
              "vendor.version %r != generator VERSION %r"
              % (t.get("vendor", {}).get("version"), vm.group(1)))
        if os.path.exists(cl):
            cm2 = re.search(r"^## \[([^\]]+)\]", open(cl, encoding="utf-8").read(), re.M)
            check(cm2 and cm2.group(1) == vm.group(1),
                  "newest CHANGELOG heading %r != generator VERSION %r"
                  % (cm2.group(1) if cm2 else None, vm.group(1)))

    if errors:
        print("FAILED (%d):" % len(errors))
        for e in errors:
            print("  -", e)
        sys.exit(1)
    print("check_template OK: %d items, %d LLD, %d graphs, %d uuid objects, "
          "%d triggers" % (len(item_keys), len(t["discovery_rules"]),
                           len(graphs), len(found), len(names)))


if __name__ == "__main__":
    main()
