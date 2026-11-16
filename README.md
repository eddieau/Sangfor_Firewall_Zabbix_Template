# Sangfor NGAF Zabbix Template

Zabbix 8.0 SNMP template for **Sangfor NGAF** firewalls, converted from Sangfor's
private `SANGFOR-MIB.txt` MIB (enterprise OID `.1.3.6.1.4.1.35047`).

Sangfor ships no official Zabbix template; this covers the pollable objects from
their vendor MIB.

## What it monitors

**Scalar items (29):**

- Device info: description, name, software version, AF version, serial number
- Health: `sfDeviceStatus` (0 = warning trigger)
- CPU: utilization 30s / 1min / 5min (trigger > `{$SANGFOR.CPU.MAX}`), core count
- Memory: total / free (kB → bytes), usage % (calculated, trigger > `{$SANGFOR.MEM.MAX}`), swap
- Sessions: current / new / total / new-per-second, online users
- Throughput: inbound / outbound system throughput
- Disk: overall system disk usage % (trigger > `{$SANGFOR.DISK.MAX}`)
- HA: enable, mode, current status, control/data link status (abnormal → HIGH
  trigger), sync state

**Low-level discovery (6 rules, 19 prototypes):**

| Discovery | Source table | Items |
| --- | --- | --- |
| Interface | `sfIfTable` (general.34) | in/out bps, in/out pps, in/out discards, IPv4 address |
| Disk | `sfDiskTable` (general.5) | size / used / avail / usage % / temperature |
| CPU core | `sfCpuCostRateTable` (general.20) | user / system / utilization % |
| Fan | `sfSysFanTable` (general.14) | speed, state (abnormal → trigger) |
| Power supply | `sfSysPowerTable` (general.15) | state (abnormal → HIGH trigger) |
| Temperature sensor | `sfTempSensorTable` (general.59) | reading |

## Requirements

- Zabbix **8.0** or newer (template format `8.0`, exported as XML)
- **SNMP v2c or later** on the NGAF (Counter64 objects are used for interface traffic)
- SNMP read community enabled on the firewall

## Installation

1. In Zabbix: **Data collection → Templates → Import**, select
   `template_sangfor_ngaf_snmp.xml`.
2. Create (or edit) the NGAF host:
   - Group: your network group (template is placed in `Templates/Network devices`)
   - Interface: **SNMP**, port 161, SNMP version 2c (or 3), community set below
3. Link the template.
4. Set the community macro on the host: `{$SANGFOR.SNMP.COMMUNITY}`
   (default in template is `public` — change it).
5. Wait for the LLD rules (default hourly) or run them now.

## Macros / thresholds

| Macro | Default | Meaning |
| --- | --- | --- |
| `{$SANGFOR.SNMP.COMMUNITY}` | `public` | SNMP community for all items |
| `{$SANGFOR.UPDATE.FREQ}` | `1m` | Item update interval |
| `{$SANGFOR.DISCOVERY.FREQ}` | `1h` | LLD interval |
| `{$SANGFOR.CPU.MAX}` | `90` | CPU % warning |
| `{$SANGFOR.CPU_CORE.MAX}` | `95` | Per-core CPU % warning |
| `{$SANGFOR.MEM.MAX}` | `90` | Memory usage % warning |
| `{$SANGFOR.DISK.MAX}` | `85` | Filesystem usage % warning |
| `{$SANGFOR.DISK_TEMP.MAX}` | `70` | Disk temperature warning |
| `{$SANGFOR.IF_DROP.MAX}` | `1000` | Interface discard rate (ps) warning |

## Known caveats (please verify against your device)

- **`sfIfInRate` / `sfIfOutRate` are instantaneous rates**, despite being typed
  `Counter64` in the MIB (verified with two-sample deltas on a live NGAF — see
  *Verified against live hardware* below). Older draft of this template wrongly
  applied *Change per second*; that has been removed.
- `sfSysIn/OutThroughput` and swap objects do not state units in the MIB; they
  are stored raw. Adjust `Units` on the item if your device reports bps or KB/s.
- Memory counters are assumed **kB**, disk counters **MB** (per MIB DESCRIPTION);
  converted to bytes via multipliers. Verify once after first poll.
- The interface LLD filter excludes names matching `l.o`, `Loopback`, `lo` only;
  tighten `{#SNMPVALUE}` filter if you have many virtual interfaces.
- Sangfor also defines **traps** in `SANGFOR-MIB-AF.txt`
  (config change, dual-active switch, interface failure, firewall-under-attack —
  OIDs under `.1.3.6.1.4.1.35047.200.200`). Trap receiving needs snmptrapd +
  Zabbix trap setup and is **not** included here.

## Verified against live hardware (2026-11-16)

Tested over SNMPv3 authPriv (SHA1/AES128) against a Sangfor NGAF running
**AF8.0.108.657 Build20260923** (nsf-1050a-i):

- `sfIfInRate`/`sfIfOutRate` **are instantaneous byte/s gauges** — two samples
  12 s apart went down on a busy interface (302 → 274). Template applies
  `×8` only (bits/s), no *Change per second*.
- `sfIfInPkts`/`sfIfOutPkts` **are cumulative counters** — template keeps
  *Change per second* (pps). Discards (.15/.16) treated as counters too.
- `sfSysMemoryUsage` (.13.5) returns a numeric string (`"56"`) that matches the
  web UI; free/total ints (.13.3/.13.4, kB) would give a higher number because
  cache/buffer counts as available. Template polls .13.5 with a regex
  extraction step — this is the usage % that matches the vendor UI.
- Disk table (.5) values are in **MB** as documented (e.g. size 3967,
  used 2205, avail 1762) — converted to bytes.
- `sfSysDiskUsage` (.52.1) returns **noSuchObject** on AF 8.0.108 — removed.
- Fan (.14), PSU (.15), temperature-sensor (.59) tables return **noSuchObject**
  on this platform — the LLD rules simply discover nothing; kept for models
  that do expose them. Delete those discovery rules if you want a clean list.
- Throughput (.48.1/.48.2) confirmed instantaneous (87→63, 96→49 in 8 s) but
  **units are not stated in the MIB** — stored raw; check against your UI and
  set Units on those two items if you identify them (likely Mbps).
- Sessions (.27), CPU (.19/.20/.21), HA (.64.1–.64.8) all poll cleanly.

## Files

- `template_sangfor_ngaf_snmp.xml` — import this into Zabbix
- `scripts/gen_template.py` — the generator used to produce the XML from the MIB
  (kept for reference / modification)

Source MIB: Sangfor `SANGFOR-MIB.txt` / `SANGFOR-MIB-AF.txt` (enterprises 35047),
downloaded from Sangfor support.

## License

MIT (see `LICENSE`).
