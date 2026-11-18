# Backlog

Accepted improvements and roadmap ideas from external reviews (2026-11-17),
triaged against the actual v0.5.0 template. Items here are NOT yet
implemented; anything shipped moves to CHANGELOG.md.

## P0 — polish — DONE in v0.5.1 (2026-11-17)

- [x] **Template-level tags** (`class: network`, `target: sangfor`,
  `component: firewall`, `vendor: Sangfor`). Item-level `component:*` tags
  already exist (54/61 items); template-level tags are the official-guideline
  gap. Generator: add `tags` to the template object.
- [x] **Explicit `trends`** on numeric items (currently 0/61 set; Zabbix
  defaults apply). Suggested: `365d` for gauges/utilization, `90d` for
  high-cardinality rates (per-interface bps/pps). Generator default + override.
- [x] **Hysteresis on threshold triggers** (CPU/memory/disk): add recovery
  expressions below the warn threshold (e.g. CPU warn >90, recover <80) to
  stop flapping. Applies to scalar + prototype thresholds.
- [x] **Explicit LLD `lifetime` / `enabled_lifetime`**: currently unset
  (8.0 defaults apply — lost resources are cleaned after the default
  lifetime, so "orphans linger forever" is not true, but explicit values
  document intent). VERIFIED 8.0 semantics: lifetime default 7d (delete),
  enabled_lifetime default 0 + enabled_lifetime_type 2 (disable
  immediately); shipped lifetime 30d / enabled_lifetime 0.

## From review #3 (2026-11-17, score 9.2/10 — mostly accurate)

Accepted:
- [x] Document sfIfTable↔IF-MIB index alignment as a firmware-verified
  assumption with a re-verification procedure (done in
  docs/compatibility.md; valid catch — alignment was verified live but
  only stated in item descriptions).
- [ ] HA split-brain composite trigger idea: `sangfor.ha.status` = slave
  AND `sangfor.ha.ctrllink` = abnormal (failed failover indicator).
  Needs semantics review against a real HA pair before shipping; single
  verified device runs standalone (HA disabled), so cannot test live.

Rejected (with evidence):
- **Patch 1 "JSNUM return null + DISCARD_UNCHANGED_HEARTBEAT"**: technically
  wrong — returning null from JS preprocessing does not produce a graceful
  skip (numeric conversion still fails), and DISCARD_UNCHANGED_HEARTBEAT is
  a value-deduplication step, NOT an error handler. If stale-value
  tolerance is ever wanted, the correct mechanism is the step's
  `error_handler: DISCARD_VALUE`; current explicit-throw behaviour is
  deliberate (visible unsupported beats silently stale usage data).
- **Patch 3 "recovery OR icmpping=1"**: would reintroduce false recovery —
  a dead SNMP agent stops trap delivery while the device still pings, so
  trap silence + ICMP up is NOT evidence the attack ended. The existing
  AND `zabbix[host,snmp,available]=1` design is deliberate; a permanently
  broken SNMP agent is surfaced by the "No SNMP data collection" trigger.
- **"Built-in dashboards provide immediate value upon import"**: false on
  8.0.0 — nested dashboards are silently dropped by configuration.import
  (documented; install_dashboard.py is the working path).
- **"~60% SNMP load reduction" from dependent items**: invented figure;
  host already uses bulk=1 GETBULK aggregation and measured load is
  negligible (see walk[] entry below).
- Note: review #3's quoted trap keys ("snmpTrapOID.0s=") lost backslashes
  in its web-extractor ingestion; the shipped keys correctly use
  `\.0\s=\s` and are live-verified.

## From review #4 (DeepSeek share link, 2026-11-18, score 8.0/10)

Accepted (pending approval, candidate v0.5.2):
- [ ] **DISCARD_UNCHANGED_HEARTBEAT (1h) on discrete-state poll items**:
  device.status, ha.enabled/mode/status/ctrllink/datalink/sync, plus
  per-interface operstatus/adminstatus and fan/psu state prototypes.
  Cuts DB writes for values that rarely change; last()-based triggers
  unaffected. MUST NOT be applied to trap items (would break nodata()
  recovery), to uptime items (change()-based restart trigger), or to
  system.name (rename trigger compares consecutive values).

Accepted as an ops note (server-side, not this template):
- [ ] Trapper-health monitoring: if snmptrapd/the Zabbix snmp trapper
  dies while SNMP polling stays up, trap silence after
  {$SANGFOR.TRAP_PROBLEM_HOURS} looks like recovery. The recovery gate
  checks SNMP availability, not trapper liveness. Mitigation belongs on
  the Zabbix server/proxy health monitoring (internal item
  zabbix[process,snmp trapper,avg,busy] / process check), not on the
  firewall template.

Rejected / stale (with evidence):
- **"Missing mandatory class/target tags"** — STALE: added in v0.5.1
  (class: network, target: sangfor, component: firewall, vendor: Sangfor;
  verified in shipped JSON). The review read the file partially.
- **"Add hysteresis to all threshold triggers"** — STALE: v0.5.1 already
  ships hysteresis on all five threshold triggers (CPU scalar + per-core,
  memory, disk space, disk temperature).
- **Patch 3 walk[] master with JSONPATH "$"** — technically wrong as
  written: raw SNMP walk output is not JSON; it needs the SNMP walk to
  JSON preprocessing step first. The architecture direction itself is
  already tracked below (walk[] master + dependent items, deferred with
  measured justification: bulk=1 GETBULK already enabled, load negligible).
- **"Make all metric triggers depend on No-SNMP trigger"** — not official
  practice; unsupported items stop producing values so last()-based
  metric triggers cannot fire new problems during an SNMP outage. The
  official dependency chain (already ported) covers ICMP/loss/response.
- **"CPU 30s history 7d is heavy, use 1d"** — 7d matches official
  templates; storage cost trivial at 1/min cadence. No change.
- **"Value map for trap severity"** — redundant: trap items are LOG text;
  severity is already expressed per-trap via trigger priority.
- **"Ensure dashboard auto-imports with template"** — impossible on
  8.0.0 (nested dashboards silently dropped by configuration.import);
  install_dashboard.py is the documented working path.

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
