# Changelog

All notable changes to this template are documented here.
Template format target: Zabbix 8.0 (JSON import).

## [0.5.2] - 2026-11-18

### Changed
- **DISCARD_UNCHANGED_HEARTBEAT (1h)** on discrete-state items: device
  status, HA enable/mode/status/ctrllink/datalink/sync (7 scalars) and the
  interface oper/admin status + fan/PSU state prototypes (4). Cuts DB
  writes for values that rarely change; `last()`-based triggers are
  unaffected. Deliberately NOT applied to trap items (would break
  `nodata()` recovery), uptime items (`change()`), or system.name
  (consecutive-value comparison). From review #4 triage.

### Upgrade notes
- Normal updateExisting re-import; discovered status items pick up the
  new preprocessing on the next LLD run.

## [0.5.1] - 2026-11-17

P0 polish from the triaged external review (see BACKLOG.md):

### Added
- Template-level tags: `class: network`, `target: sangfor`,
  `component: firewall`, `vendor: Sangfor` (official-guideline alignment;
  item-level component tags unchanged).
- Explicit `trends` on all numeric items/prototypes: `365d` for gauges and
  utilization, `90d` for high-cardinality per-interface rates
  (bps/pps/drops). Previously relied on Zabbix defaults.
- Hysteresis on the five threshold triggers (CPU scalar + per-core, memory,
  disk space, disk temperature): recovery expressions at 90% of the warn
  threshold (temperature: -5°C) so values hovering at the threshold do not
  flap. Trap/ICMP/uptime triggers unchanged.
- Explicit LLD `lifetime: 30d` + `enabled_lifetime: 0` on all six discovery
  rules: lost resources disable immediately (8.0 default behaviour, now
  explicit) and are deleted after 30d instead of the 7d default, keeping
  history of vanished interfaces longer.

### Upgrade notes
- Normal `updateExisting` re-import updates everything in place (UUIDs
  unchanged). Already-discovered items pick up the new trends values on the
  next LLD run (verified live: forced run flipped interface rates to 90d).

## [0.5.0] - 2026-11-17

### Changed
- **Per-interface link state replaces trap-pair alerting.** The MIB defines
  no varbinds for the link/interface notifications and real device samples
  carry no interface identifier, so per-trap-pair triggers could not track
  per-interface state (WAN1 recovery cleared WAN2's problem). The two
  fail/normal trap pairs are now event-log items (no trigger); the
  interface LLD gains IF-MIB `ifOperStatus`/`ifAdminStatus` prototypes
  (verified exposed on AF8.0.108, indexes match sfIfTable) and a
  per-interface `link down` trigger prototype: oper=down AND admin=up AND
  `{$SANGFOR.IF.LINK.ALERT:"<ifname>"}=1`. Recovery is automatic per
  interface. Detection latency = one poll interval; traps still logged
  instantly.
- New macro `{$SANGFOR.IF.LINK.ALERT}` (default 0, opt-in per critical
  port via context macro) - avoids alert spam from unused admin-enabled
  ports.
- Valuemaps added: `Sangfor: if oper status`, `Sangfor: if admin status`.

### Added
- check_template.py validates context macros ({$X:"ctx"}) against defined
  macro base names.

### Upgrade notes
- Re-import with `triggers.deleteMissing: true` to remove the two old
  pair triggers ("Interface link failure", "Link failure alert").
- Enable link alerting on critical ports with host context macros, e.g.
  {$SANGFOR.IF.LINK.ALERT:"eth1"} = 1.

## [0.4.0] - 2026-11-17

External code-review follow-up. Behaviour fixes first:

### Fixed
- **Trap routing anchored**: named trap item keys previously matched the
  bare MIB notification name anywhere in the trap text. Since Zabbix
  copies a trap to EVERY matching item, payload text containing another
  trap name would double-route it. Keys are now regexes anchored on the
  `snmpTrapOID.0 = <MIB>::<name>` varbind line.
- **ICMP loss trigger**: `min(key,{$ICMP_LOSS_MIN_OCCURRENCES})` was
  silently a *3-second time window* (function arg without `#` = seconds),
  so one bad poll fired the alert. Now the official
  `min(...,5m)>{$ICMP_LOSS_WARN} and min(...,5m)<100`; response time
  aligned to official `avg(...,5m)`. Macro `{$ICMP_LOSS_MIN_OCCURRENCES}`
  removed.
- **"System name has changed" could never recover** (`nodata(...,1d)` on a
  15-min-polled item, and no manual close): now official-style
  `manual_close: YES`, no recovery expression, `last(#1)<>last(#2)` form.
- **"No SNMP data collection" fired on a single transient failure**: now
  `max(...,{$SNMP.TIMEOUT})=0` (new macro, default 5m).
- **Dashboard graph widgets all shared `reference: AAAAA`** - references
  must be unique per dashboard; each widget now gets a deterministic
  unique 5-char reference.
- **JAVASCRIPT numeric extraction** now throws on empty/non-numeric input
  instead of emitting garbage into a numeric item.

### Changed
- Trap items are `value_type LOG` (Zabbix parses the trap timestamp
  instead of receive time). `coldStart` added as defensive event-log item.
- Official trigger dependency chain ported: loss -> unavailable,
  response time -> loss + unavailable, restart -> No-SNMP.
- Valuemaps added: device status, HA enable/mode/status/sync, fan/PSU
  state (Latest data + dashboard show words, not raw numbers).
- Static info items (descr/name/versions) poll at `{$SANGFOR.INFO.FREQ}`
  instead of 1m; HA enable/mode keep 31d history so changes are visible.
- Graph axes: Sessions new/s moved to right axis; per-interface Discards
  graph draws on the left axis.
- README trap-routing wording corrected ("first match" -> copies to all
  matching items); item counts 60 -> 61 (coldStart).

### Added
- `scripts/check_template.py`: full integrity suite (UUID hygiene across
  all objects, all `{$MACRO}` uses defined, trigger/graph/dashboard
  references resolve, trap keys anchored, widget references unique,
  page objects contain only `widgets`).
- CI: `permissions: contents: read`, SHA-pinned actions, runs
  check_template.py + py_compile, keeps the generator/JSON drift guard.

### Notes
- Trap item keys changed, but item/trigger UUIDs are seeded from the short
  trap names (unchanged), so a normal `updateExisting` re-import updates
  keys/expressions IN PLACE and history is preserved - no `deleteMissing`
  purge needed. (Verified: all 16 v0.3 trap trigger UUIDs identical in
  v0.4.) Note: TEXT->LOG value_type change leaves pre-upgrade values in
  the old history table; new values land in history_log.
- The known 8.0.0 nested-dashboard import gap and the two-pass first
  import remain upstream issues; install_dashboard.py still required.

## [0.3.0] - 2026-11-17

### Added
- **Template graphs (4)**: CPU utilization (30s/1m/5m), Memory
  (total/free/usage % dual-axis), Sessions (current + new/s), Throughput
  (in/out).
- **Per-interface graph prototypes (2)** on `sangfor.if.discovery`:
  `Interface {#SNMPVALUE}: Traffic` (in/out bps) and
  `Interface {#SNMPVALUE}: Discards` - 32 graphs materialize via LLD on a
  16-port NGAF (verified live).
- **Dashboard "Sangfor NGAF"** (2 pages): Overview (device info, CPU/Memory
  gauges, sessions/status/HA/uptime tiles, Throughput + Sessions graphs) and
  Health (CPU + Memory graphs). Shipped as a template-nested dashboards
  block AND installable via `scripts/install_dashboard.py`.
- `scripts/install_dashboard.py` - resolves template item/graph references
  against your real NGAF host and imports a standalone dashboard document
  through the API (idempotent).

### Known Zabbix 8.0.0 limitations (documented + worked around)
- `configuration.import` silently DROPS template-nested dashboards in all
  three formats (JSON/XML/YAML) - verified empirically; the official
  templates' dashboards predate this. Use `install_dashboard.py` for now;
  keep the nested block for forward compatibility.
- `dashboard.create` API widget-field type codes are numeric
  (0=INTEGER 2=STRING 4=ITEM 5=ITEM_PROTOTYPE 6=GRAPH) and differ from the
  import-format string constants; `hide_header` is not accepted there.
- Template-level `graphs` must be top-level `zabbix_export.graphs`
  (nested-under-template `graphs` tag is rejected); `drawtype` must be
  omitted for plain LINE (the literal constant "LINE" is rejected).

## [0.2.1] - 2026-11-17

### Added
- GitHub Actions CI (`.github/workflows/verify-template.yml`): regenerates
  the template with `scripts/gen_template.py` and fails if the committed
  `template_sangfor_ngaf_snmp.json` differs, plus JSON sanity checks
  (object counts, duplicate-UUID guard). The generator and the shipped JSON
  can no longer drift apart silently.

### Changed
- Unpaired trap triggers now recover only when the silence window has
  elapsed **and** `zabbix[host,snmp,available]=1`: a collector/network
  outage no longer looks like "attack ended" (review follow-up).
- README: explicit ⚠️ example of the per-trap-pair (not per-interface)
  pairing limitation; trap item counts corrected (20 named + fallback).

## [0.2.0] - 2026-11-16

### Added
- Standalone coverage: ported all useful items/triggers from the standard
  "Network Generic Device by SNMP" template (ICMP ping/loss/response, RFC1213
  system info ×5, network + hardware uptime, `zabbix[host,snmp,available]`,
  `snmptrap.fallback`). The generic template is no longer required.
- Full Sangfor trap coverage matching the NGAF web-UI trap list: 20 named
  `snmptrap[]` items across `sfGeneralTrap` (35047.110.x),
  `sfFirewallTraps` (35047.200.200.x) and `SNMPv2-MIB::warmStart`.
- `{$SANGFOR.TRAP_PROBLEM_HOURS}` macro (default `4h`) — configurable
  auto-recovery window for unpaired trap problems.

### Changed
- Trap trigger recovery redesign:
  - Fail/Normal pairs (`sfFirewallTrapIfFail`/`sfFirewallTrapIfNormal`,
    `sfLinkDownTrap`/`sfLinkUpTrap`) now share one item each and recover on
    the matching recovery trap instead of a fixed 24 h `nodata()` window.
  - Pure informational traps (config change, rulebase update, database
    update, warm start) are event-log items with **no trigger**.
- Throughput objects confirmed **kbps** on live AF8.0.108 — now multiplied by
  1000 and stored with `Units=bps`.
- Interface discard prototypes units `ps` → `pps`.
- Generator UUIDs are now content-seeded (stable per object identity); the
  previous sequential-counter scheme renumbered UUIDs whenever an object was
  inserted or removed.
- Generator output path is repository-relative (`pathlib`), so a fresh clone
  can regenerate without editing the script.

### Removed
- `{$SANGFOR.SNMP.COMMUNITY}` macro (Zabbix 8.0 template items have no
  community field; credentials live on the host SNMP interface).
- Non-functional `{$ICMP_COUNT}`, `{$ICMP_TIMEOUT}`, `{$ICMP_LOSS_SAMPLES}`
  macros (they were never wired into the Simple-check keys).
- `sfSysDiskUsage` (`.52.1`) item — returns `noSuchObject` on AF 8.0.108.

## [0.1.0] - 2026-11-16

### Added
- Initial template converted from Sangfor's private `SANGFOR-MIB.txt`
  (enterprises 35047): 28 scalar items, 6 LLD rules (interface, disk, CPU
  core, fan, PSU, temperature), 13 triggers.
- Verified against a live NGAF AF8.0.108.657 (nsf-1050a-i) over SNMPv3
  authPriv (SHA1/AES128) behind a Zabbix proxy.
- Proved and documented vendor quirks: `sfIfInRate`/`sfIfOutRate` are
  instantaneous byte/s gauges despite Counter64 typing; memory/disk integers
  in kB/MB; `sfSysMemoryUsage` string must be used to match the vendor UI.
