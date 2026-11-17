# Troubleshooting

## Items show "Invalid update interval {$SANGFOR.…}"

The host lost its inherited template macros. Usual cause: the template was
unlinked/deleted while host items became orphans (e.g. an API unlink that
left items behind), or the template was deleted and re-imported without
relinking.

Fix: verify `Data collection → Hosts → <host> → Templates` lists
**Sangfor NGAF by SNMP**, and that the template's Macros tab shows
`{$SANGFOR.*}`. If items are orphaned (no owning template), delete the host
and recreate it with the template linked from the start.

## Named trap items stay empty although traps arrive

The anchored keys assume the **official `zabbix/zabbix-snmptraps` bash
handler output format**: a line exactly like
`SNMPv2-MIB::snmpTrapOID.0 = SANGFOR-MIB::sfCPUWarnTrap`. If you use a
Perl receiver (`snmpTrapOID.0 type=6 value=OID: ...`) or SNMPTT with a
different format, the anchored regexes miss and everything lands in
`snmptrap.fallback`. Either standardise on the bash handler (recommended,
what this template is tested with) or rewrite the key regexes to match
your receiver's format. The regexes also hard-code the MIB **module
names** `SANGFOR-MIB` (110.x family, from SANGFOR-MIB-COMPATIBLE.txt) and
`SANGFOR-AF-MIB` (200.200.x family) - verified against the vendor files;
if your MIB copies declare different module names, adjust accordingly.

## Real device traps arrive but never reach the host (source-IP NAT)

Docker's userland-proxy SNATs published UDP ports: a trap from
192.0.2.1 to host:162 can appear inside the container as coming from the
bridge gateway (e.g. 172.18.0.1), so Zabbix matches no host interface and
drops the trap (it does NOT go to fallback - fallback only applies once a
host matched). Diagnose with a privileged capture on the host
(`tcpdump -ni any udp port 162`) vs the ZBXTRAP line in snmptraps.log.
Fixes, in order of preference:

1. Run `zabbix-snmptraps` with `network_mode: host` (no NAT, real source
   preserved). The image listens on **1162/udp** (fixed; a non-root
   container cannot bind 162 in host mode), so point the device's trap
   destination at port **1162**. Verified working.
2. Disable docker's userland-proxy daemon-wide
   (`/etc/docker/daemon.json: {"userland-proxy": false}` + docker
   restart) - keeps port 162 but restarts every container on the host.

## Traps land in `snmptrap.fallback` instead of the named items

1. **MIB not loaded.** The trap text must contain `SANGFOR-MIB::sf...` or
   `SANGFOR-AF-MIB::sf...`. Check the receiver:
   `grep snmpTrapOID /var/lib/zabbix/snmptraps/snmptraps.log`. If OIDs are
   numeric, mount `SANGFOR-MIB.txt` (from `SANGFOR-MIB-COMPATIBLE.txt`) and
   `SANGFOR-AF-MIB.txt` (from `SANGFOR-MIB-AF.txt`) into the
   zabbix-snmptraps container's `/var/lib/zabbix/mibs` and restart it.
2. **Source IP mismatch.** Traps are matched to hosts by source address vs
   the host's SNMP interface IP. A NAT/relay in front of the firewall, or a
   locally injected test trap (shows the docker bridge gateway like
   `172.17.0.1`), matches nothing. Trap senders inside the firewall itself
   (e.g. from the collector host) always look like the bridge — test from a
   real device or temporarily use `snmptrap.fallback`.
3. **Host monitored by a proxy?** The trap chain (`snmptrapd` +
   `StartSNMPTrapper=1` + shared volume) must run on the **proxy**, not the
   server.

## Interface traffic graphs look wrong

`sfIfInRate`/`sfIfOutRate` are instantaneous byte/s gauges on current
firmware (confirmed by two-sample deltas that went *down* between polls).
Do not add *Change per second* to them — `×8` to bits/s is correct. If your
firmware behaves differently (values only ever increase), remove the
multiplier and add *Change per second* + `×8`.

`sfIfInPkts`/`sfIfOutPkts`/drops *are* cumulative — they keep
*Change per second*.

## "No SNMP data collection" fires while the device is alive

Check `zabbix[host,snmp,available]` in Latest data plus the proxy/server log.
Common causes: SNMP v3 credentials changed on the device, the device's SNMP
service access list no longer includes the collector IP, or UDP 161/162
firewalled between collector and device.

## LLD discovers nothing (interfaces/disks/CPU cores empty)

Sangfor private tables are read via the host's SNMP interface — verify
manual first:

```bash
snmpwalk -v3 -l authPriv -u USER -a SHA -A '...' -x AES -X '...' \
  <ngaf-ip> .1.3.6.1.4.1.35047.1.34.1.2     # sfIfName column
```

If the walk returns values, check the LLD rule's `filter` and the item
`{$SANGFOR.DISCOVERY.FREQ}`; run the discovery manually from the rule's
checkbox ("Test"/"Run now").

## First import on a brand-new Zabbix aborts

`"...depends on trigger ..., which does not exist"` is a known 8.0 import
ordering quirk for the No-SNMP → ICMP dependency. Run the identical import
again — the second pass succeeds.

## Upgrading the template

Re-import the newer JSON with **Update existing** enabled (API
`configuration.import` with `createMissing`+`updateExisting` rules does
this). UUIDs are content-seeded, so objects update in place; discovered
items are kept. Review `CHANGELOG.md` for threshold/semantics changes after
upgrading.
