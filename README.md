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

- **`sfIfInRate` / `sfIfOutRate` semantics are ambiguous in the MIB.** They are
  typed `Counter64` with a "byte/s" description. This template treats them as
  accumulated byte counters and applies *Change per second × 8* to get bits/s.
  If your firmware already returns an instantaneous rate and the values look
  wrong, remove the preprocessing steps on those item prototypes.
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

## Files

- `template_sangfor_ngaf_snmp.xml` — import this into Zabbix
- `scripts/gen_template.py` — the generator used to produce the XML from the MIB
  (kept for reference / modification)

Source MIB: Sangfor `SANGFOR-MIB.txt` / `SANGFOR-MIB-AF.txt` (enterprises 35047),
downloaded from Sangfor support.

## License

MIT (see `LICENSE`).
