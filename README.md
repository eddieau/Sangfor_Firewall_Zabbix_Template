# Sangfor NGAF Zabbix Template

Zabbix **8.0** SNMP template for **Sangfor NGAF** firewalls, converted from
Sangfor's private `SANGFOR-MIB.txt` MIB (enterprise OID `1.3.6.1.4.1.35047`).

Sangfor ships no official Zabbix template. This one is **standalone**: it also
includes the useful checks from the standard "Network Generic Device by SNMP"
template (ICMP availability, RFC1213 system info, uptimes, SNMP availability,
trap fallback), so you do NOT need to link that template as well.

Built and **verified against a live NGAF** (AF8.0.108.657, nsf-1050a-i) over
SNMPv3 authPriv, monitored through a Zabbix proxy.

## What it monitors

The template contains **61 template-level items in total: 28 Sangfor scalar
items, 22 SNMP trap items (21 named + the `snmptrap.fallback` catch-all),
and 11 ported generic checks:**

- Device info: description, name, software version, AF version, serial
  (serial ships DISABLED — `sfSnGW` is not implemented on AF 8.0.108)
- Health: `sfDeviceStatus` (0 = warning trigger)
- CPU: utilization 30s / 1min / 5min (trigger > `{$SANGFOR.CPU.MAX}`), core count
- Memory: total / free (kB → bytes), usage % from the device's own
  `sfSysMemoryUsage` (matches the vendor UI; trigger > `{$SANGFOR.MEM.MAX}`), swap
- Sessions: current / new / total / new-per-second, online users
- Throughput: inbound / outbound system throughput (device reports kbps;
  stored as bps via `×1000`)
- HA: enable, mode, current status, control/data link status (abnormal → HIGH
  trigger), sync state
- SNMP traps — 21 named `snmptrap[...]` items covering the trap list the
  NGAF web UI actually offers (plus `coldStart` and `snmptrap.fallback`).
  Keys are regexes **anchored on the `snmpTrapOID.0` varbind line** — see
  trap routing below:

  | UI alert | OID | MIB notification | priority |
  | --- | --- | --- | --- |
  | Temperature Alert | 35047.110.1 | sfTemperatureWarnTrap | HIGH |
  | CPU Alert | 35047.110.2 | sfCPUWarnTrap | WARNING |
  | Memory Alert | 35047.110.3 | sfMemoryWarnTrap | WARNING |
  | Hard Disk Alert | 35047.110.4 | sfDiskWarnTrap | HIGH |
  | Power Alert | 35047.110.5 | sfPowerWarnTrap | HIGH |
  | Interface Alert | 35047.110.6 | sfInterfaceDownTrap | HIGH |
  | Fan Alert | 35047.110.7 | sfFanWarnTrap | HIGH |
  | HA Status Alert | 35047.110.8 | sfHAStatusTrap | HIGH |
  | Database Update Alert | 35047.110.17 | sfRuleBaseUpgradeTrap | INFO |
  | Passthrough Status Alert | 35047.110.19 | sfBypassChangeTrap | WARNING |
  | Link Recovery Alert | 35047.110.23 | sfLinkUpTrap | INFO |
  | Link Failure Alert | 35047.110.24 | sfLinkDownTrap | HIGH |
  | Insufficient Port Resources | 35047.110.25 | sfPortResourceWarnTrap | WARNING |
  | SLA-based Link Failover | 35047.110.27 | sfSLATrap | WARNING |
  | Firewall Attacked Alert | 35047.200.200.6 | sfFirewallTrapFwAttack | HIGH |
  | Protected Network Attacked | 35047.200.200.7 | sfFirewallTrapNetworkAttack | HIGH |
  | Warm Start Alert | 1.3.6.1.6.3.1.1.5.2 | warmStart (SNMPv2-MIB) | INFO |
  | (extras not in the UI list) | 35047.200.200.1–.5 | ConfChange / RulebaseUpdate / DualSwitch / If-Fail-Normal pair | mixed |
  | (defensive) | 1.3.6.1.6.3.1.1.5.1 | coldStart (SNMPv2-MIB, event log) | - |

**Trap trigger design (v0.2.0, anchored routing v0.4.0):**

Trap items are `value_type=LOG` so Zabbix parses the trap's own timestamp.
Named keys are anchored regexes on the `snmpTrapOID.0` varbind line.

- **Link fail/normal traps are event-log items (v0.5.0)** —
  `sfFirewallTrapIfFail|sfFirewallTrapIfNormal` and
  `sfLinkDownTrap|sfLinkUpTrap` each share one LOG item with **no trigger**.
  Why: the MIB defines no varbinds for these notifications and real device
  samples carry no interface identifier, so trap-based pairing could only
  track the pair as a whole (WAN1 up would clear WAN2's problem).
- **Per-interface link alerting is done by POLLING instead (v0.5.0):** the
  interface LLD adds `ifOperStatus` + `ifAdminStatus` prototypes (standard
  IF-MIB, verified exposed; indexes match `sfIfTable`). The trigger
  `Interface {#SNMPVALUE}: link down` fires per interface when
  oper=down AND admin=up AND `{$SANGFOR.IF.LINK.ALERT:"<ifname>"}=1`, and
  recovers automatically when the link comes back. WAN1/WAN2 states are
  fully independent. Detection latency = one poll interval (default 1m);
  the trap items still record events instantly in Latest data.
  ⚠️ **Opt-in by design:** the macro defaults to 0 because unused but
  admin-enabled ports would otherwise alert. Enable it per critical port
  with a context macro, e.g. `{$SANGFOR.IF.LINK.ALERT:"eth1"} = 1`.

  **Different sites wire different ports** (one uses eth0, another only
  eth9/eth10) - do NOT copy one site's macros to another. Use the helper to
  configure each host from its LIVE state:

  ```bash
  export ZABBIX_URL=https://your-zabbix.example.com/api_jsonrpc.php
  export ZABBIX_API_KEY=...
  python3 scripts/configure_link_alerts.py --all            # dry-run
  python3 scripts/configure_link_alerts.py --all --apply    # commit
  ```

  It enables exactly the physical ports currently UP (in use), removes
  macros for idle/down ports, and always keeps VPN tunnels
  (vpntun/ssltun*/veth*) silent. Re-run after any re-cabling. A known-
  critical port that is down RIGHT NOW is not auto-enabled - enable it
  manually once confirmed. Note: because status items use
  DISCARD_UNCHANGED_HEARTBEAT, a macro change alone re-evaluates the
  trigger only on the next value change or 1h heartbeat; to clear a stale
  problem immediately, disable+re-enable that discovered trigger.
- **Unpaired problem traps** (attacks, dual switch, temperature/CPU/memory/
  disk/power/interface/fan/HA/bypass/port/SLA) recover after
  `{$SANGFOR.TRAP_PROBLEM_HOURS}` (default 4 h) of trap silence — but only
  while SNMP polling is still alive (`zabbix[host,snmp,available]=1`).
  Sangfor re-sends active alerts (verified: attack traps every ~10 s), so
  silence usually means the condition ended. If the collector or the
  network dies at the same time, silence is NOT evidence of recovery and
  the problem stays open.
- **Pure informational events** (config changed, rulebase updated, database
  update, warm/cold start) have **no trigger** — the trap is stored as the item
  value (event-log style); view it in Latest data or add your own trigger.
- Because `snmptrap.fallback` lives here, **do not link "Network Generic
  Device by SNMP" on the same host** — Zabbix refuses the duplicate
  `snmptrap.fallback` key.

**Ported generic checks (11)** — why the generic template is no longer needed:

- ICMP ping / loss / response time (Simple checks, official-style triggers)
- System contact / description / location / name / object ID (RFC1213-MIB;
  name-change trigger included)
- Uptime network + hardware (timeticks → seconds; restart trigger requires
  BOTH counters to drop, suppressing false SNMP-stack-only resets)
- `zabbix[host,snmp,available]` + "No SNMP data collection" trigger, which
  depends on the ICMP-unavailable trigger to avoid double alerts

**Low-level discovery (6 rules, 19 prototypes):**

| Discovery | Source table | Items |
| --- | --- | --- |
| Interface | `sfIfTable` (general.34) + IF-MIB | in/out bit/s, in/out pps, in/out discards, IPv4 address, oper/admin status + per-interface link-down trigger |
| Disk | `sfDiskTable` (general.5) | size / used / avail / device-reported usage % / temperature |
| CPU core | `sfCpuCostRateTable` (general.20) | user / system / utilization % |
| Fan | `sfSysFanTable` (general.14) | speed, state (abnormal → trigger) |
| Power supply | `sfSysPowerTable` (general.15) | state (abnormal → HIGH trigger) |
| Temperature sensor | `sfTempSensorTable` (general.59) | reading |

## Graphs & Dashboard (v0.3.0)

The template ships with **4 template graphs** (CPU utilization, Memory,
Sessions, Throughput) and **2 per-interface graph prototypes** (Traffic,
Discards) that LLD instantiates for every discovered interface.

It also contains a **"Sangfor NGAF" dashboard** (2 pages: Overview +
Health: device info tiles, CPU/Memory gauges, sessions/status/HA/uptime,
graph widgets).

⚠️ **Zabbix 8.0.0 quirk**: `configuration.import` silently DROPS
template-nested dashboards (verified on JSON, XML and YAML imports - official
templates' dashboards were seeded by the distributor, not through this API
path). Until that is fixed upstream, install the dashboard with the helper
script, which rewrites the template item/graph references to your real host
and imports a standalone dashboard document:

```bash
export ZABBIX_URL=https://your-zabbix.example.com/api_jsonrpc.php
export ZABBIX_API_KEY=***
python3 scripts/install_dashboard.py --host "your-ngaf-host-name"
```

The dashboard block stays inside the template JSON for forward
compatibility; once your Zabbix build supports nested dashboard import you
can skip the script.

## Requirements

- Zabbix **8.0** or newer (JSON import format matches 8.0 exactly)
- **SNMP v2c or later** on the NGAF (Counter64 objects are used). SNMPv3
  authPriv (SHA1/AES128) verified working.
- SNMP read access enabled on the firewall

## Installation

1. In Zabbix: **Data collection → Templates → Import**, select
   `template_sangfor_ngaf_snmp.json` (works with JSON; the 8.0 XML flavour
   changed several tags, so JSON is shipped).
2. Create the host (**Firewalls** group or your own), then add an
   **SNMP interface**:
   - SNMP version: v3 (or v2c)
   - For v3: Security name, Security level `authPriv`, Auth protocol SHA +
     passphrase, Privacy protocol AES128 + passphrase, Context name empty
   - Tick **Use combined requests** (bulk GETBULK — recommended; Sangfor
     responds well to bulk walks)
   - Note: in Zabbix 8.0 template items have **no community/security-name
     field**; all SNMP credentials live on the host interface.
3. Link the template (create the SNMP interface **before** linking, or Zabbix
   refuses the item inheritance with "a host interface of type SNMP is
   required").
4. Wait for the first poll; LLD rules run on creation and then every
   `{$SANGFOR.DISCOVERY.FREQ}`.

Via the API, interfaces are embedded in `host.create` / `host.update`
(`hostinterface.create` no longer exists in 8.0):

```json
"interfaces": [{"type":"2","main":"1","useip":"1","ip":"192.0.2.1",
  "port":"161","details":{"version":"3","bulk":"1",
    "securityname":"USER","securitylevel":"2",
    "authprotocol":"1","authpassphrase":"...","privprotocol":"1",
    "privpassphrase":"...","contextname":""}}]
```

## Macros / thresholds

| Macro | Default | Meaning |
| --- | --- | --- |
| `{$SANGFOR.UPDATE.FREQ}` | `1m` | Item update interval |
| `{$SANGFOR.DISCOVERY.FREQ}` | `1h` | LLD interval |
| `{$SANGFOR.CPU.MAX}` | `90` | CPU % warning |
| `{$SANGFOR.CPU_CORE.MAX}` | `95` | Per-core CPU % warning |
| `{$SANGFOR.MEM.MAX}` | `90` | Memory usage % warning |
| `{$SANGFOR.DISK.MAX}` | `85` | Filesystem usage % warning |
| `{$SANGFOR.DISK_TEMP.MAX}` | `70` | Disk temperature (°C) warning |
| `{$SANGFOR.IF_DROP.MAX}` | `1000` | Interface discard rate (drops/s) warning |
| `{$SANGFOR.INFO.FREQ}` | `15m` | System-info item interval |
| `{$SANGFOR.UPTIME.FREQ}` | `1m` | Uptime poll interval (restart detection) |
| `{$SANGFOR.IF.NAME.MATCHES}` | `.*` | Interface discovery: include regex |
| `{$SANGFOR.IF.NAME.NOT_MATCHES}` | `^$` | Interface discovery: exclude regex (e.g. `^(veth\|ssltun\|vpntun)`) |
| `{$SANGFOR.TRAP_PROBLEM_HOURS}` | `4h` | Auto-recovery window for unpaired trap problems |
| `{$ICMP_LOSS_WARN}` | `20` | ICMP loss (%) warning (5 m window) |
| `{$ICMP_RESPONSE_TIME_WARN}` | `0.15` | Avg response time (s) warning (5 m avg) |
| `{$SNMP.TIMEOUT}` | `5m` | How long SNMP polling may be down before "No SNMP data collection" fires |
| `{$SANGFOR.IF.LINK.ALERT}` | `0` | Opt-in per-interface link-down alerting; set `=1` with interface-name context on critical ports |

## SNMP trap receiving (optional)

The template includes trap items, but receiving traps requires a trap chain
in front of the Zabbix server **or the proxy that monitors the host** (see
Zabbix 8.0 manual, "SNMP trap" item type). For a proxy-monitored host the
trapper runs on the proxy:

1. `snmptrapd` (e.g. the official `zabbix/zabbix-snmptraps` container)
   listens on UDP 162; its bundled `zabbix_trap_handler.sh` writes received
   traps to `snmptraps.log` in a volume **shared with the zabbix-server or
   zabbix-proxy container** (`/var/lib/zabbix/snmptraps`).
2. Zabbix server/proxy runs with `StartSNMPTrapper=1` and
   `SNMPTrapperFile=/var/lib/zabbix/snmptraps/snmptraps.log`
   (docker: env `ZBX_STARTSNMPTRAPPER=1`, `ZBX_SNMPTRAPPERFILE=...`).
3. The trapper matches each trap's source address against the host's SNMP
   interface IP, then **copies the trap to EVERY `snmptrap[regexp]` item
   whose key regex matches the trap text** (not just the first - official
   behaviour); anything unmatched goes to `snmptrap.fallback`. Because of
   the copy-to-all semantics this template anchors every named trap regex
   on the `snmpTrapOID.0 = <MIB>::<name>` varbind line, so payload text
   (interface names, descriptions) can never double-route a trap.
4. **Mount BOTH vendor MIB files** into the receiver's
   `/var/lib/zabbix/mibs` (rename them to valid module filenames):

   | Vendor file | Mount as | Provides trap names for |
   | --- | --- | --- |
   | `SANGFOR-MIB-COMPATIBLE.txt` | `SANGFOR-MIB.txt` | the `sfGeneralTrap` family — all 14 of the NGAF UI's 35047.**110.x** alerts |
   | `SANGFOR-MIB-AF.txt` | `SANGFOR-AF-MIB.txt` | the `sfFirewallTraps` family — 35047.**200.200.x** |

   The named trap items route on MIB notification names, so **both**
   files are required: mount only one and the other family's traps still
   arrive but print numerically, miss their named items, and pile into
   `snmptrap.fallback`. (Note `SANGFOR-MIB-COMPATIBLE.txt` declares the
   same `SANGFOR-MIB` module - that is intentional; it is the file that
   contains the 110.x definitions.) Restart the receiver after mounting.
5. Configure the NGAF itself (web UI) to send traps to the collector
   (server or proxy) IP:162 with its trap community (e.g. v2c). The
   `zabbix-snmptraps` image runs `snmptrapd` with `disableAuthorization yes`,
   so any community is accepted — restrict at snmptrapd / network level if
   that matters to you.
6. **Source-IP caveat:** traps sent from the proxy host itself (or through
   Docker's userland proxy on a published port) show a bridge-gateway source
   like `172.17.0.1` and match no host. Real LAN traps keep the device IP and
   route correctly. To test locally, send the trap with the receiver on
   `--network host`, or temporarily accept it via `snmptrap.fallback`.

## Relationship to "Network Generic Device by SNMP"

This template **replaces** it: its 11 generic pollable items + triggers are
already ported into the 61 template-level items counted above (28 Sangfor
scalar + 22 trap + 11 generic = 61 - the generic checks are part of the 61,
not additional). Link only this template (both templates on one host fails
on the duplicate `snmptrap.fallback` key). Overlap with the old generic
checks is only informational: `system.descr` (sysDescr) ≈ `sfDeviceDescr`.

**First import into a brand-new Zabbix**: the "No SNMP data collection"
trigger dependency can abort the import with
`"...depends on trigger ..., which does not exist"` — just run the same
import a second time; the referenced triggers now exist and it resolves.
(Verified on 8.0.0.)

## Verified against live hardware (AF8.0.108.657 nsf-1050a-i)

**v0.4.0 trap-path re-verification (2026-11-17):** anchored routing tested
end-to-end with synthetic traps carrying `snmpTrapAddress.0 = <device IP>`:
`35047.110.1` (SANGFOR-MIB family) and `35047.200.200.6` (SANGFOR-AF-MIB
family) each landed in their NAMED items (not fallback) and raised
problems; `110.24` link-down raised the pair problem and `110.23` link-up
RECOVERED it. Both MIB module names confirmed against the vendor files
(`SANGFOR-MIB`, `SANGFOR-AF-MIB`). v0.4.0 adds coldStart + anchored trap
keys (61 template items); in-place upgrade preserved trap history
(UUIDs unchanged).

**v0.2-era baseline (2026-11-16):** all enabled items (then 60 template +
~163 discovered) polled clean through Zabbix proxy 8.0 — ICMP Simple checks
and `zabbix[host,snmp,available]` both work proxy-side; 0 unsupported.
Real Sangfor traps from the device arrived, resolved to MIB names and
routed into the named trap items end-to-end. Findings:

- `sfIfInRate`/`sfIfOutRate` **are instantaneous byte/s gauges** despite being
  typed Counter64 — two samples 12 s apart went *down* (302 → 274). Template
  applies `×8` only (bits/s), **no** *Change per second*.
- `sfIfInPkts`/`sfIfOutPkts`/discards **are cumulative counters** —
  *Change per second* is correct there.
- `sfSysMemoryUsage` (`.13.5`) returns a numeric string (`"56"`) matching the
  vendor UI; free/total ints would show ~80% instead because cache/buffer
  counts as available. Polled with a JAVASCRIPT numeric-extraction step.
  (A `REGEX` preprocessing step with the optional second "output" parameter
  misbehaved on this Zabbix build and returned the parameter itself — the
  JAVASCRIPT step avoids the issue.)
- Disk usage % is read from the device's own `sfDiskUsedPercent` column
  (`.5.1.6`, string) instead of a calculated item, and `/dev/loop*` entries
  are filtered out.
- Memory ints are **kB**, disk ints **MB** as documented; converted to bytes.
- `sfSysDiskUsage` (`.52.1`) and `sfSnGW` (`.40`) return **noSuchObject** —
  the first is not included at all; the serial item ships disabled.
- Fan (`.14`), PSU (`.15`), temperature-sensor (`.59`) tables return
  **noSuchObject** on nsf-1050a-i; the LLD rules discover nothing and stay
  quiet. Kept for models that do expose them — delete if unwanted.
- Throughput (`.48.1/.48.2`) confirmed instantaneous (87→63, 96→49 in 8 s);
  **units = kbps (operator-confirmed 2026-11-16)** — template applies
  MULTIPLIER 1000 and stores as bps, so graphs render "x kbps" correctly.
- Trap receive chain verified end-to-end on a proxy host with the official
  `zabbix/zabbix-snmptraps` container + shared volume + `StartSNMPTrapper=1`:
  a synthetic `35047.110.1` trap arrived in `snmptraps.log` as
  `SNMPv2-MIB::snmpTrapOID.0 = SANGFOR-MIB::sfTemperatureWarnTrap` and the
  proxy's snmp trapper read the shared file. See caveats in "SNMP trap
  receiving".

## Files

- `template_sangfor_ngaf_snmp.json` — import this into Zabbix 8.0
- `scripts/gen_template.py` — the generator (deterministic **content-seeded**
  UUIDs: each object's uuid derives from its own key/name, so re-import
  updates objects in place and adding/removing items never renumbers the
  rest)
- `docs/compatibility.md`, `docs/troubleshooting.md` — field notes
- `CHANGELOG.md` — version history

## MIB files and licensing

The Sangfor MIB files are **not included** in this repository. Users must
obtain `SANGFOR-MIB.txt`, `SANGFOR-MIB-COMPATIBLE.txt` and
`SANGFOR-MIB-AF.txt` directly from Sangfor support / the vendor download
portal and comply with the vendor's licensing and redistribution terms.
The MIT license in this repository applies to the original template JSON,
generator script and documentation only.

See **[docs/mibs.md](docs/mibs.md)** for the exact file versions this
template was verified against (SHA-256 manifest), how to verify your
copies, and how to install them into the trap receiver. Polling needs no
MIB files at all — they are only required for trap name resolution.

## Disclaimer

This project is **unofficial** and is not affiliated with, endorsed by, or
supported by Sangfor Technologies. Zabbix and Sangfor are trademarks of
their respective owners.

## License

MIT (see `LICENSE`).
