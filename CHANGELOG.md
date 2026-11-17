# Changelog

All notable changes to this template are documented here.
Template format target: Zabbix 8.0 (JSON import).

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
