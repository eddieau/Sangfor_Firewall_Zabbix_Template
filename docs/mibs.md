# Sangfor MIB files: obtaining, verifying, installing

## Why the MIB files are not in this repository

The Sangfor MIB files are **vendor-proprietary material** distributed by
Sangfor (support portal / appliance download). They carry no explicit
redistribution license, so this repository does not bundle them; the MIT
license here covers only the original template, generator, scripts and
documentation. Obtain the files directly from Sangfor and comply with
their terms.

**Polling does not need any MIB files** — every item uses numeric OIDs.
MIBs are only needed on the **trap receiver** so `snmptrapd` resolves trap
OIDs to the notification names the template's anchored keys match on.

## Required files (exact versions this template was verified against)

| Vendor file | Mount into receiver as | MIB module | SHA-256 |
| --- | --- | --- | --- |
| `SANGFOR-MIB-COMPATIBLE.txt` (LAST-UPDATED 202003110000Z) | `SANGFOR-MIB.txt` | `SANGFOR-MIB` | `6522045b03a1405394f76cf8a5d2f14fb3479ce03a12ac24407d945121437efe` |
| `SANGFOR-MIB-AF.txt` (LAST-UPDATED 201311200000Z) | `SANGFOR-AF-MIB.txt` | `SANGFOR-AF-MIB` | `8a06e74dc30890232c41eaa4360e63af4ecbf1aef7731263bcab5ac41023750a` |

Notes:

- `SANGFOR-MIB-COMPATIBLE.txt` intentionally declares the same
  `SANGFOR-MIB` module as the plain `SANGFOR-MIB.txt` in the vendor bundle,
  but it is the file that contains the `sfGeneralTrap` **110.x**
  notification names (Temperature/CPU/Memory/Disk/Power/Interface/Fan/HA/
  DB-update/Bypass/Link/Port-resource/SLA). Use it, not the plain one.
- `SANGFOR-MIB-AF.txt` provides the `sfFirewallTraps` **200.200.x** names
  (config change, dual switch, rulebase, if fail/normal, attacks).
- If Sangfor publishes newer revisions the hashes will differ; the
  notification names must still match the anchored trap keys (see
  docs/troubleshooting.md if traps land in fallback).
- The vendor zip also contains the standard net-snmp MIB collection
  (IF-MIB, SNMPv2-*, RFC1213, ...). You do **not** need to install those:
  the `zabbix/zabbix-snmptraps` image already ships the IETF/IANA MIBs.

## Verify your copies

```bash
sha256sum SANGFOR-MIB-COMPATIBLE.txt SANGFOR-MIB-AF.txt
# compare against the table above
```

## Install into the trap receiver

For the official `zabbix/zabbix-snmptraps` container, mount a host
directory as `/var/lib/zabbix/mibs` containing the two renamed files:

```bash
mkdir -p mibs
cp SANGFOR-MIB-COMPATIBLE.txt mibs/SANGFOR-MIB.txt
cp SANGFOR-MIB-AF.txt        mibs/SANGFOR-AF-MIB.txt
# compose:  - ./mibs:/var/lib/zabbix/mibs:ro   (then recreate the container)
```

Verify resolution after restart — a received trap must log a line like:

```
SNMPv2-MIB::snmpTrapOID.0 = SANGFOR-MIB::sfCPUWarnTrap
```

If it prints numeric OIDs instead, the MIBs are not loaded (wrong mount,
wrong filename, or module name mismatch) and all named trap items will sit
idle while traps pile into `snmptrap.fallback`.
