# Backlog

Accepted improvements and roadmap ideas from external reviews (2026-11-17),
triaged against the actual v0.5.0 template. Items here are NOT yet
implemented; anything shipped moves to CHANGELOG.md.

## P0 — polish (small, safe, next minor release)

- [ ] **Template-level tags** (`class: network`, `target: sangfor`,
  `component: firewall`, `vendor: Sangfor`). Item-level `component:*` tags
  already exist (54/61 items); template-level tags are the official-guideline
  gap. Generator: add `tags` to the template object.
- [ ] **Explicit `trends`** on numeric items (currently 0/61 set; Zabbix
  defaults apply). Suggested: `365d` for gauges/utilization, `90d` for
  high-cardinality rates (per-interface bps/pps). Generator default + override.
- [ ] **Hysteresis on threshold triggers** (CPU/memory/disk): add recovery
  expressions below the warn threshold (e.g. CPU warn >90, recover <80) to
  stop flapping. Applies to scalar + prototype thresholds.
- [ ] **Explicit LLD `lifetime` / `enabled_lifetime`**: currently unset
  (8.0 defaults apply — lost resources are cleaned after the default
  lifetime, so "orphans linger forever" is not true, but explicit values
  document intent). VERIFY 8.0 `enabled_lifetime` semantics (0 vs duration)
  before choosing values; do not copy review snippets blindly.

## P1 — considered (needs design/verification first)

- [ ] **walk[] master + dependent items** for sfIfTable / disk / CPU-core
  tables (Zabbix 8.0 SNMP walk preprocessing). Biggest remaining efficiency
  opportunity on high-port-count devices. NOTE: host interfaces already use
  `bulk=1` (combined GETBULK requests), so current chatter is already
  reduced; this is an optimization, not a defect fix. Large refactor —
  target v0.6.0, keep per-item keys/UUIDs stable where possible.
- [ ] **HA group-table LLD** (`sfHAGroupTable`, general.64.9): MIB defines
  it, but first do a read-only walk on the reference device to confirm the
  firmware implements it (fan/PSU/temp tables turned out empty the same
  way). Add only if real data exists.
- [ ] **Macro/filter to disable hardware LLD rules** (fan/PSU/temp) on
  models that don't expose them. Empty-table behaviour is already
  documented (README + docs/compatibility.md) and silent; this is optional
  operator convenience.
- [ ] **Swap units**: still "as reported by device" — verify against the
  vendor UI / memory values on a live device, then set units + multiplier.

## P2 — roadmap ideas (nice-to-have, no commitment)

- [ ] Grafana dashboard JSON (official Zabbix datasource plugin) + short
  integration note. Native Zabbix dashboard already ships with the template.
- [ ] Webhook/media-type examples formatting Sangfor trap events (attack,
  HA, bypass) for chat platforms.
- [ ] "Health score" calculated item (weighted CPU + memory + session
  pressure + HA state + recent critical traps).
- [ ] Dashboard page "Security events" surfacing attack/rulebase/config
  trap items.
- [ ] HA-pair awareness: suppress/informational certain triggers on the
  standby unit (needs a reliable standby indicator; `sfHACurStatus` exists).
- [ ] VPN tunnel object discovery beyond interface-level (MIB exposes no
  per-tunnel session table on AF8.0; only `sfIpsecStatusTrap` — revisit on
  newer firmware).

## Rejected / already done (do not re-litigate)

- **Trap pairing not per-interface** — FIXED in v0.5.0: fail/normal trap
  pairs are event-log items (no triggers); authoritative per-interface
  link alerting polls IF-MIB ifOperStatus/ifAdminStatus (opt-in context
  macro). Review #2 still listed this as a gap; that claim is stale.
- **Legacy XML schema / deprecated `{host:key.last()}` syntax / missing
  LLD / missing tags / missing MIB docs / missing snmptrapd integration /
  enterprise OID 22274** (review #1) — all factually wrong for this repo:
  JSON 8.0 export, 33/33 modern trigger expressions, 6 LLD rules,
  component tags, full MIB table + troubleshooting docs, live-verified
  trap chain, enterprise OID 35047. Review #1's sample XML would not
  import (invalid `recovery_mode` constant, missing uuids, JSONPath on
  raw walk output).
- **Custom on-fail = discard for all preprocessing** (review #1) —
  rejected: items going unsupported on SNMP failure is correct, visible
  behaviour covered by the "No SNMP data collection" trigger; discarding
  values would silently mask outages. JSNUM already throws explicitly on
  non-numeric input.
- **fan/PSU/temp empty-result documentation** (review #2) — already
  documented in README and docs/compatibility.md.
