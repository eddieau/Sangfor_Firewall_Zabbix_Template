# Sangfor NGAF Zabbix Template

Zabbix **8.0** SNMP template for **Sangfor NGAF** firewalls, converted from
Sangfor's private `SANGFOR-MIB.txt` MIB (enterprise OID `1.3.6.1.4.1.35047`).

Sangfor ships no official Zabbix template; this covers the pollable objects
from their vendor MIB. Built and **verified against a live NGAF**
(AF8.0.108.657, nsf-1050a-i) over SNMPv3 authPriv.

## What it monitors

**Scalar items (28) + SNMP trap items (7):**

- Device info: description, name, software version, AF version, serial
  (serial ships DISABLED — `sfSnGW` is not implemented on AF 8.0.108)
- Health: `sfDeviceStatus` (0 = warning trigger)
- CPU: utilization 30s / 1min / 5min (trigger > `{$SANGFOR.CPU.MAX}`), core count
- Memory: total / free (kB → bytes), usage % from the device's own
  `sfSysMemoryUsage` (matches the vendor UI; trigger > `{$SANGFOR.MEM.MAX}`), swap
- Sessions: current / new / total / new-per-second, online users
- Throughput: inbound / outbound system throughput (units not stated in MIB)
- HA: enable, mode, current status, control/data link status (abnormal → HIGH
  trigger), sync state
- SNMP traps (`SANGFOR-MIB-AF.txt`, OIDs under `1.3.6.1.4.1.35047.200.200`):
  7 named `snmptrap[<name>]` items (config change INFO, HA dual-switch HIGH,
  rulebase update INFO, interface normal INFO, interface fail HIGH, firewall
  under attack HIGH, protected network under attack HIGH). Triggers auto-
  recover via `nodata(...,1d)`. There is deliberately **no**
  `snmptrap.fallback` here — the standard "Network Generic Device by SNMP"
  template ships one, and Zabbix refuses to link two templates that both
  define the same trap key. Unmatched traps land in the generic fallback.

**Low-level discovery (6 rules, 19 prototypes):**

| Discovery | Source table | Items |
| --- | --- | --- |
| Interface | `sfIfTable` (general.34) | in/out bit/s, in/out pps, in/out discards, IPv4 address |
| Disk | `sfDiskTable` (general.5) | size / used / avail / device-reported usage % / temperature |
| CPU core | `sfCpuCostRateTable` (general.20) | user / system / utilization % |
| Fan | `sfSysFanTable` (general.14) | speed, state (abnormal → trigger) |
| Power supply | `sfSysPowerTable` (general.15) | state (abnormal → HIGH trigger) |
| Temperature sensor | `sfTempSensorTable` (general.59) | reading |

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
| `{$SANGFOR.IF_DROP.MAX}` | `1000` | Interface discard rate (ps) warning |

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
   interface IP, then routes it to the first `snmptrap[regexp]` item whose
   key parameter matches the trap text; anything unmatched goes to
   `snmptrap.fallback`.
4. For readable trap names, mount `SANGFOR-MIB-AF.txt` (as
   `SANGFOR-AF-MIB.txt`) into the snmptrapd MIBs dir — trap items here match
   on the `sfFirewall*` MIB names, so keep the MIB loaded. If the MIB is
   missing, traps still arrive in `snmptrap.fallback` as numeric OIDs.
5. Configure the NGAF itself (web UI) to send traps to the collector
   (server or proxy) IP:162. No auth is applied by Zabbix itself; control
   access at snmptrapd / network level.

## Coexistence with "Network Generic Device by SNMP"

This template is designed to link **alongside** the generic one (verified):

- Generic gives: ICMP availability (3 items), standard system info,
  `hrSystemUptime`, `snmptrap[$1]` + `snmptrap.fallback`.
- Sangfor template adds the private-MIB metrics (sessions, HA, per-core CPU,
  interface rates as the vendor reports them, named SF trap items).
- Slight overlap only: `system.descr` ≈ `sfDeviceDescr`; no trigger clashes.

## Verified against live hardware (2026-11-16, AF8.0.108.657 nsf-1050a-i)

All 191 items (28 + 163 discovered) poll clean; only findings:

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
- Throughput (`.48.1/.48.2`) confirmed instantaneous (87→63, 96→49 in 8 s),
  but **units are not stated in the MIB** — stored raw; set Units on those
  two items once you identify them (likely Mbps).
- Sangfor also defines **traps** in `SANGFOR-MIB-AF.txt` (config change,
  dual-active switch, interface failure, firewall-under-attack — OIDs under
  `1.3.6.1.4.1.35047.200.200`). Trap receiving needs snmptrapd + Zabbix trap
  setup and is **not** included here.

## Files

- `template_sangfor_ngaf_snmp.json` — import this into Zabbix 8.0
- `scripts/gen_template.py` — the generator (deterministic uuid5 UUIDs so
  re-import updates objects in place; keep generation order stable when
  editing)

Source MIB: Sangfor `SANGFOR-MIB.txt` / `SANGFOR-MIB-AF.txt`
(enterprises 35047), downloaded from Sangfor support.

## License

MIT (see `LICENSE`).
