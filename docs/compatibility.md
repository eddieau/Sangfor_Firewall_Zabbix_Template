# Compatibility

Tested against the combinations below. Everything else is best-effort:
Sangfor's private MIB coverage varies per model and firmware.

| NGAF model | Firmware | Transport | Zabbix | Result |
| --- | --- | --- | --- | --- |
| nsf-1050a-i | AF8.0.108.657 Build20260923 (SangforOS.4.9.4) | SNMPv3 authPriv (SHA1/AES128) via Zabbix proxy 8.0 | 8.0.0 (Docker) | Fully working: 60 template items + ~163 discovered, 0 unsupported; live traps received and routed |

## Known coverage differences by firmware (from the one verified device)

- `sfSysDiskUsage` (.52.1) → `noSuchObject` — not polled by this template.
- `sfSnGW` (.40) serial → `noSuchObject` — item ships **disabled**.
- Fan (.14) / PSU (.15) / temperature-sensor (.59) tables → `noSuchObject`
  on nsf-1050a-i (hardware tables likely only exposed on redundant-PSU or
  larger chassis). The LLD rules stay silent — delete them if your model
  also lacks these.
- The device sends `sfGeneralTrap` (35047.**110.x**) traps in addition to
  the documented `sfFirewallTraps` (35047.200.200.x); the web UI trap list
  mixes both families — this template covers both.

- **Restart trigger requires BOTH uptimes**: `sysUpTime` (RFC1213) AND
  `hrSystemUptime` (HOST-RESOURCES-MIB). Models without `hrSystemUptime`
  get an unsupported hardware-uptime item, and the restart trigger then
  silently never fires — re-verify it when testing a new model.
- **Interface index alignment is a firmware-verified assumption, not a
  guarantee**: the interface LLD discovers names from the proprietary
  `sfIfTable` (35047.1.34) but polls link state from standard IF-MIB
  `ifOperStatus`/`ifAdminStatus` using the same `{#SNMPINDEX}`. On
  AF8.0.108.657 the indexes match exactly (eth0–eth10 = 1–11, tunnels =
  122–126, verified by walking both tables). On other models/firmware,
  re-verify with `snmpwalk ... 35047.1.34.1.2` vs `1.3.6.1.2.1.31.1.1.1.1`
  before trusting per-interface link alerts; a mismatch would attach
  link state to the wrong interface.

## SNMP version notes

- Counter64 objects (`sfIf*Rate`, `sfIf*Pkts`, `sfIf*Drop`) require
  **SNMP v2c or later**. v1 will show those items as not supported.
- SNMPv3 authPriv verified working (SHA1 + AES128, level authPriv).
- `get[Bulk]`-style fetches respond well; "Use combined requests" (bulk) is
  recommended and was used throughout testing.

## Zabbix version notes

- JSON import format targets **8.0**. On 7.x most objects import, but
  trigger dependency import and `value_type` semantics differ; no support
  claim is made for <8.0.
- Monitored directly or through a proxy: trap *receiving* must run on the
  node that monitors the host (server → server; proxy → proxy).

If you validate this template on another NGAF model/firmware, please open
an issue or PR adding a row to the table above.
