#!/usr/bin/env python3
"""Generate Zabbix 8.0 template (JSON import format) from Sangfor MIB (enterprises 35047).

Format verified against configuration.export output of an official 8.0 template.
"""
import uuid, json
from pathlib import Path

BASE = "1.3.6.1.4.1.35047"        # sangfor
GEN = BASE + ".1"                  # general ::= { sangfor 1 }
TPL = "Sangfor NGAF by SNMP"
TGROUP = "Templates/Network devices"

# Deterministic content-seeded UUIDs so re-importing a regenerated file
# updates objects in place. Each object's uuid is seeded from its OWN
# stable identifier (key/name), so inserting or removing objects never
# shifts the identity of unrelated ones (Zabbix 8.0 import requires the
# UUIDv4 layout).
_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/eddieau/Sangfor_Firewall_Zabbix_Template")

def _fakev4(seed):
    """Deterministic UUID forced into UUIDv4 layout (Zabbix 8.0 import
    validates the version nibble, so raw uuid5 hex is rejected)."""
    b = bytearray(uuid.uuid5(_NS, seed).bytes)
    b[6] = (b[6] & 0x0F) | 0x40          # version 4
    b[8] = (b[8] & 0x3F) | 0x80          # variant 10
    return uuid.UUID(bytes=bytes(b)).hex

def U(name):
    return _fakev4("sangfor-ngaf-" + name)

items = []
drs = []
macros = []

def snmp_item(name, key, oid, vtype="FLOAT", units="", desc="", pre=None,
              trig=None, tags=(), history="7d"):
    it = {"uuid": U("item-" + key), "name": name, "type": "SNMP_AGENT", "snmp_oid": oid,
          "key": key, "delay": "{$SANGFOR.UPDATE.FREQ}",
          "history": history, "value_type": vtype, "description": desc}
    if units:
        it["units"] = units
    if pre:
        it["preprocessing"] = pre
    if tags:
        it["tags"] = [{"tag": a, "value": b} for a, b in tags]
    if trig:
        it["triggers"] = [trig]
    items.append(it)
    return it

def calc_item(name, key, formula, units="", desc="", vtype="FLOAT",
              trig=None, tags=()):
    it = {"uuid": U("item-" + key), "name": name, "type": "CALCULATED", "key": key,
          "delay": "1m", "params": formula, "history": "7d",
          "value_type": vtype, "description": desc}
    if units:
        it["units"] = units
    if tags:
        it["tags"] = [{"tag": a, "value": b} for a, b in tags]
    if trig:
        it["triggers"] = [trig]
    items.append(it)

def TR(prio, expr, name):
    return {"uuid": U("trig-" + name), "expression": expr, "name": name,
            "priority": prio}

# preprocessing helpers
def P(t, *params):
    d = {"type": t}
    if params:
        d["parameters"] = list(params)
    return d

X8 = [P("MULTIPLIER", "8")]                       # instant byte/s -> bit/s
CPS = [P("CHANGE_PER_SECOND")]                    # cumulative -> rate
K2B = [P("MULTIPLIER", "1024")]
M2B = [P("MULTIPLIER", "1048576")]
# NOTE: a REGEX step with a second "output type" parameter misbehaves on
# this Zabbix build (echoed the constant). Numeric extraction from strings is
# done with a JAVASCRIPT step instead (verified approach).
JSNUM = [P("JAVASCRIPT", "return value.replace(/[^0-9.]/g, '');")]

# ================= scalar items =================
snmp_item("Sangfor: Device description", "sangfor.device.descr",
          "get[" + GEN + ".1.0]", "CHAR",
          desc="sfDeviceDescr.")
snmp_item("Sangfor: Device name", "sangfor.device.name",
          "get[" + GEN + ".17.0]", "CHAR",
          desc="sfSysDevName.")
snmp_item("Sangfor: Software version", "sangfor.software.version",
          "get[" + GEN + ".18.0]", "CHAR",
          desc="sfSysSoftVersion.")
snmp_item("Sangfor: AF version", "sangfor.af.version",
          "get[" + GEN + ".24.0]", "CHAR",
          desc="afSysSoftVersion.")
_serial = snmp_item("Sangfor: Serial number", "sangfor.serial.number",
          "get[" + GEN + ".40.0]", "CHAR",
          desc="sfSnGW - serial number of the appliance. Not implemented on "
               "AF8.0.108 (nsf-1050a-i): item ships DISABLED to avoid "
               "unsupported-noise; enable it if your model exposes sfSnGW.")
_serial["status"] = "DISABLED"

snmp_item("Sangfor: Device status", "sangfor.device.status",
          "get[" + GEN + ".12.0]",
          desc="sfDeviceStatus: 0 - Warning, 1 - Normal.",
          tags=[("component", "health")],
          trig=TR("WARNING", "last(/%s/sangfor.device.status)=0" % TPL,
                  "Sangfor: Device reports WARNING status on {HOST.NAME}"))

snmp_item("Sangfor: CPU utilization (30s)", "sangfor.cpu.util.30s",
          "get[" + GEN + ".19.4.0]", units="%",
          desc="sfCpuAllCostRateLast30Sec.", tags=[("component", "cpu")])
snmp_item("Sangfor: CPU utilization (1 min)", "sangfor.cpu.util.1m",
          "get[" + GEN + ".19.5.0]", units="%",
          desc="sfCpuAllCostRateLast1Min.", tags=[("component", "cpu")],
          trig=TR("AVERAGE",
                  "last(/%s/sangfor.cpu.util.1m)>{$SANGFOR.CPU.MAX}" % TPL,
                  "Sangfor: High CPU utilization over {$SANGFOR.CPU.MAX}% on {HOST.NAME}"))
snmp_item("Sangfor: CPU utilization (5 min)", "sangfor.cpu.util.5m",
          "get[" + GEN + ".19.6.0]", units="%",
          desc="sfCpuAllCostRateLast5Min.", tags=[("component", "cpu")])
snmp_item("Sangfor: CPU core count", "sangfor.cpu.num",
          "get[" + GEN + ".21.0]",
          desc="sfCpuNum.", tags=[("component", "cpu")])

snmp_item("Sangfor: Memory total", "sangfor.mem.total",
          "get[" + GEN + ".13.4.0]", units="B", pre=K2B,
          desc="sfIntSysTotalMemory (kB, converted to bytes).",
          tags=[("component", "memory")])
snmp_item("Sangfor: Memory free", "sangfor.mem.free",
          "get[" + GEN + ".13.3.0]", units="B", pre=K2B,
          desc="sfIntSysFreeMemory (kB, converted to bytes).",
          tags=[("component", "memory")])
snmp_item("Sangfor: Memory usage", "sangfor.mem.util",
          "get[" + GEN + ".13.5.0]", units="%", pre=JSNUM,
          desc="sfSysMemoryUsage - device-reported usage % (string, matches "
               "vendor UI; free/total ints would over-count cache/buffer).",
          tags=[("component", "memory")],
          trig=TR("AVERAGE",
                  "last(/%s/sangfor.mem.util)>{$SANGFOR.MEM.MAX}" % TPL,
                  "Sangfor: High memory usage over {$SANGFOR.MEM.MAX}% on {HOST.NAME}"))
snmp_item("Sangfor: Swap total", "sangfor.swap.total",
          "get[" + GEN + ".38.1.0]",
          desc="sfMemTotalSwap. Units as reported by device.")
snmp_item("Sangfor: Swap available", "sangfor.swap.avail",
          "get[" + GEN + ".38.2.0]",
          desc="sfMemAvailSwap. Units as reported by device.")

snmp_item("Sangfor: Current sessions", "sangfor.sessions.current",
          "get[" + GEN + ".27.3.0]", desc="sfCurSession.",
          tags=[("component", "sessions")])
snmp_item("Sangfor: New sessions", "sangfor.sessions.new",
          "get[" + GEN + ".27.1.0]", desc="sfNewSessions.",
          tags=[("component", "sessions")])
snmp_item("Sangfor: Total sessions", "sangfor.sessions.total",
          "get[" + GEN + ".27.2.0]", desc="sfTotalSessions.",
          tags=[("component", "sessions")])
snmp_item("Sangfor: New sessions per second", "sangfor.sessions.new.persec",
          "get[" + GEN + ".27.4.0]", desc="sfNewSessionPerSec.",
          tags=[("component", "sessions")])
snmp_item("Sangfor: Online users", "sangfor.users",
          "get[" + GEN + ".23.0]", desc="sfUsers.",
          tags=[("component", "users")])

snmp_item("Sangfor: Inbound throughput", "sangfor.throughput.in",
          "get[" + GEN + ".48.2.0]", "FLOAT", "bps",
          desc="sfSysInThroughput - instantaneous kbps (confirmed by operator "
               "2026-11-16); multiplied by 1000 for bps display.",
          pre=[P("MULTIPLIER", "1000")],
          tags=[("component", "throughput")])
snmp_item("Sangfor: Outbound throughput", "sangfor.throughput.out",
          "get[" + GEN + ".48.1.0]", "FLOAT", "bps",
          desc="sfSysOutThroughput - instantaneous kbps (confirmed by operator "
               "2026-11-16); multiplied by 1000 for bps display.",
          pre=[P("MULTIPLIER", "1000")],
          tags=[("component", "throughput")])

snmp_item("Sangfor: HA enabled", "sangfor.ha.enabled",
          "get[" + GEN + ".64.1.0]",
          desc="sfHAEnable: 0 - disabled, 1 - enabled.",
          tags=[("component", "ha")], history="0")
snmp_item("Sangfor: HA mode", "sangfor.ha.mode",
          "get[" + GEN + ".64.2.0]",
          desc="sfHAMode: 0 - invalid, 1 - master-master, 2 - master-slave, "
               "3 - mirror.", tags=[("component", "ha")], history="0")
snmp_item("Sangfor: HA current status", "sangfor.ha.status",
          "get[" + GEN + ".64.3.0]",
          desc="sfHACurStatus: 0 - invalid, 1 - init, 4 - master, 5 - slave.",
          tags=[("component", "ha")])
snmp_item("Sangfor: HA control link status", "sangfor.ha.ctrllink",
          "get[" + GEN + ".64.6.0]",
          desc="sfHACtrlLinkStatus: 0 - invalid, 1 - normal, 2 - abnormal.",
          tags=[("component", "ha")],
          trig=TR("HIGH", "last(/%s/sangfor.ha.ctrllink)=2" % TPL,
                  "Sangfor: HA control link ABNORMAL on {HOST.NAME}"))
snmp_item("Sangfor: HA data link status", "sangfor.ha.datalink",
          "get[" + GEN + ".64.7.0]",
          desc="sfHADataLinkStatus: 0 - invalid, 1 - normal, 2 - abnormal.",
          tags=[("component", "ha")],
          trig=TR("HIGH", "last(/%s/sangfor.ha.datalink)=2" % TPL,
                  "Sangfor: HA data link ABNORMAL on {HOST.NAME}"))
snmp_item("Sangfor: HA sync state", "sangfor.ha.sync",
          "get[" + GEN + ".64.8.0]",
          desc="sfHASyncState: 0 - invalid, 1 - sync running, 2 - sync end, "
               "3 - unknown.", tags=[("component", "ha")])

# ================= LLD =================
IF = GEN + ".34.1"    # sfIfTable
DK = GEN + ".5.1"     # sfDiskTable
CC = GEN + ".20.1"    # sfCpuCostRateTable
FN = GEN + ".14.1"    # sfSysFanTable
PW = GEN + ".15.1"    # sfSysPowerTable
TS = GEN + ".59.1"    # sfTempSensorTable

def proto(name, key, oid, units="", pre=None, vtype="FLOAT", desc="",
          tags=(), trig=None):
    it = {"uuid": U("proto-" + key), "name": name, "type": "SNMP_AGENT",
          "snmp_oid": "get[" + oid + "]", "key": key,
          "delay": "{$SANGFOR.UPDATE.FREQ}",
          "history": "7d", "value_type": vtype, "description": desc}
    if units:
        it["units"] = units
    if pre:
        it["preprocessing"] = pre
    if tags:
        it["tags"] = [{"tag": a, "value": b} for a, b in tags]
    if trig:
        it["_trig"] = trig
    return it

def calc_proto(name, key, formula, units="", desc="", tags=(), trig=None):
    it = {"uuid": U("item-" + key), "name": name, "type": "CALCULATED", "key": key,
          "delay": "1m", "params": formula, "history": "7d",
          "value_type": "FLOAT", "description": desc}
    if units:
        it["units"] = units
    if tags:
        it["tags"] = [{"tag": a, "value": b} for a, b in tags]
    if trig:
        it["_trig"] = trig
    return it

def lld(name, key, disc_oid, protos, desc="", filter=None):
    dr = {"uuid": U("lld-" + key), "name": name, "type": "SNMP_AGENT",
          "snmp_oid": disc_oid, "key": key,
          "delay": "{$SANGFOR.DISCOVERY.FREQ}",
          "description": desc,
          "filter": {"evaltype": "AND"} if not filter else
                    {"evaltype": "AND", "conditions": filter}}
    ips, tps = [], []
    for p in protos:
        t = p.pop("_trig", None)
        if t:
            tps.append(t)
        ips.append(p)
    dr["item_prototypes"] = ips
    if tps:
        dr["trigger_prototypes"] = tps
    drs.append(dr)

lld("Interface discovery", "sangfor.if.discovery",
    "discovery[{#SNMPVALUE}," + IF + ".2]",
    [
     proto("Interface {#SNMPVALUE}: Inbound traffic",
           "sangfor.if.in.bps[{#SNMPINDEX}]", IF + ".8.{#SNMPINDEX}",
           "bps", X8, desc="sfIfInRate - instantaneous byte/s (verified on "
           "AF8.0.108), x8 to bit/s.", tags=[("component", "network")]),
     proto("Interface {#SNMPVALUE}: Outbound traffic",
           "sangfor.if.out.bps[{#SNMPINDEX}]", IF + ".9.{#SNMPINDEX}",
           "bps", X8, desc="sfIfOutRate - instantaneous byte/s (verified on "
           "AF8.0.108), x8 to bit/s.", tags=[("component", "network")]),
     proto("Interface {#SNMPVALUE}: Inbound packets",
           "sangfor.if.in.pps[{#SNMPINDEX}]", IF + ".13.{#SNMPINDEX}",
           "pps", CPS, desc="sfIfInPkts (cumulative counter -> packets/s).",
           tags=[("component", "network")]),
     proto("Interface {#SNMPVALUE}: Outbound packets",
           "sangfor.if.out.pps[{#SNMPINDEX}]", IF + ".14.{#SNMPINDEX}",
           "pps", CPS, desc="sfIfOutPkts (cumulative counter -> packets/s).",
           tags=[("component", "network")]),
     proto("Interface {#SNMPVALUE}: Inbound discards",
           "sangfor.if.in.drop[{#SNMPINDEX}]", IF + ".15.{#SNMPINDEX}",
           "pps", CPS, desc="sfIfInDrop (cumulative counter -> drops/s).",
           tags=[("component", "network")],
           trig=TR("WARNING",
                   "last(/%s/sangfor.if.in.drop[{#SNMPINDEX}])>{$SANGFOR.IF_DROP.MAX}" % TPL,
                   "Interface {#SNMPVALUE}: high inbound discard rate on {HOST.NAME}")),
     proto("Interface {#SNMPVALUE}: Outbound discards",
           "sangfor.if.out.drop[{#SNMPINDEX}]", IF + ".16.{#SNMPINDEX}",
           "pps", CPS, desc="sfIfOutDrop (cumulative counter -> drops/s).",
           tags=[("component", "network")],
           trig=TR("WARNING",
                   "last(/%s/sangfor.if.out.drop[{#SNMPINDEX}])>{$SANGFOR.IF_DROP.MAX}" % TPL,
                   "Interface {#SNMPVALUE}: high outbound discard rate on {HOST.NAME}")),
     proto("Interface {#SNMPVALUE}: IPv4 address",
           "sangfor.if.ipv4[{#SNMPINDEX}]", IF + ".4.{#SNMPINDEX}",
           vtype="CHAR", desc="sfIfAddr.", tags=[("component", "network")]),
    ],
    desc="Interfaces from SANGFOR-MIB::sfIfTable (sfIfName column).")

lld("Disk discovery", "sangfor.disk.discovery",
    "discovery[{#SNMPVALUE}," + DK + ".2]",
    [
     proto("Disk {#SNMPVALUE}: Total space", "sangfor.disk.size[{#SNMPINDEX}]",
           DK + ".7.{#SNMPINDEX}", "B", M2B,
           desc="sfIntDiskSize (MB -> bytes).", tags=[("component", "disk")]),
     proto("Disk {#SNMPVALUE}: Used space", "sangfor.disk.used[{#SNMPINDEX}]",
           DK + ".8.{#SNMPINDEX}", "B", M2B,
           desc="sfIntDiskUsed (MB -> bytes).", tags=[("component", "disk")]),
     proto("Disk {#SNMPVALUE}: Available space", "sangfor.disk.avail[{#SNMPINDEX}]",
           DK + ".9.{#SNMPINDEX}", "B", M2B,
           desc="sfIntDiskAvail (MB -> bytes).", tags=[("component", "disk")]),
     proto("Disk {#SNMPVALUE}: Space usage", "sangfor.disk.pused[{#SNMPINDEX}]",
           DK + ".6.{#SNMPINDEX}", "%", pre=JSNUM,
           desc="sfDiskUsedPercent - device-reported usage (string).",
           tags=[("component", "disk")],
           trig=TR("WARNING",
                   "last(/%s/sangfor.disk.pused[{#SNMPINDEX}])>{$SANGFOR.DISK.MAX}" % TPL,
                   "Disk {#SNMPVALUE}: space usage over {$SANGFOR.DISK.MAX}% on {HOST.NAME}")),
     proto("Disk {#SNMPVALUE}: Temperature", "sangfor.disk.temp[{#SNMPINDEX}]",
           DK + ".10.{#SNMPINDEX}", "\u00b0C",
           desc="sfDiskTemp.", tags=[("component", "disk")],
           trig=TR("WARNING",
                   "last(/%s/sangfor.disk.temp[{#SNMPINDEX}])>{$SANGFOR.DISK_TEMP.MAX}" % TPL,
                   "Disk {#SNMPVALUE}: high temperature ({ITEM.LASTVALUE1}) on {HOST.NAME}")),
    ],
    desc="Filesystems from SANGFOR-MIB::sfDiskTable (sfFilesystemName column).",
    filter=[{"macro": "{#SNMPVALUE}", "value": "/dev/loop",
             "operator": "NOT_MATCHES_REGEX"}])

lld("CPU core discovery", "sangfor.cpu.discovery",
    "discovery[{#SNMPVALUE}," + CC + ".1]",
    [
     proto("CPU core {#SNMPVALUE}: User time", "sangfor.cpu.user[{#SNMPINDEX}]",
           CC + ".2.{#SNMPINDEX}", "%", desc="sfCpuUser per core.",
           tags=[("component", "cpu")]),
     proto("CPU core {#SNMPVALUE}: System time", "sangfor.cpu.sys[{#SNMPINDEX}]",
           CC + ".3.{#SNMPINDEX}", "%", desc="sfCpuSys per core.",
           tags=[("component", "cpu")]),
     proto("CPU core {#SNMPVALUE}: CPU utilization", "sangfor.cpu.util[{#SNMPINDEX}]",
           CC + ".4.{#SNMPINDEX}", "%", desc="sfCpuAll per core.",
           tags=[("component", "cpu")],
           trig=TR("WARNING",
                   "last(/%s/sangfor.cpu.util[{#SNMPINDEX}])>{$SANGFOR.CPU_CORE.MAX}" % TPL,
                   "CPU core {#SNMPVALUE}: utilization over {$SANGFOR.CPU_CORE.MAX}% on {HOST.NAME}")),
    ],
    desc="Per-core load from SANGFOR-MIB::sfCpuCostRateTable.")

lld("Fan discovery", "sangfor.fan.discovery",
    "discovery[{#SNMPVALUE}," + FN + ".2]",
    [
     proto("Fan {#SNMPVALUE}: Speed", "sangfor.fan.speed[{#SNMPINDEX}]",
           FN + ".3.{#SNMPINDEX}", "rpm", desc="sfFanSpeed.",
           tags=[("component", "hardware")]),
     proto("Fan {#SNMPVALUE}: State", "sangfor.fan.state[{#SNMPINDEX}]",
           FN + ".4.{#SNMPINDEX}", desc="sfFanState: 0 - abnormal, 1 - normal.",
           tags=[("component", "hardware")],
           trig=TR("AVERAGE",
                   "last(/%s/sangfor.fan.state[{#SNMPINDEX}])=0" % TPL,
                   "Sangfor: Fan {#SNMPVALUE} ABNORMAL on {HOST.NAME}")),
    ],
    desc="Fans from SANGFOR-MIB::sfSysFanTable. Some NGAF models do not "
         "expose this table (verified empty on AF8.0.108 nsf-1050a-i).")

lld("Power supply discovery", "sangfor.psu.discovery",
    "discovery[{#SNMPVALUE}," + PW + ".2]",
    [
     proto("PSU {#SNMPVALUE}: State", "sangfor.psu.state[{#SNMPINDEX}]",
           PW + ".3.{#SNMPINDEX}", desc="sfPowerState: 0 - abnormal, 1 - normal.",
           tags=[("component", "hardware")],
           trig=TR("HIGH",
                   "last(/%s/sangfor.psu.state[{#SNMPINDEX}])=0" % TPL,
                   "Sangfor: Power supply {#SNMPVALUE} ABNORMAL on {HOST.NAME}")),
    ],
    desc="PSUs from SANGFOR-MIB::sfSysPowerTable. Some NGAF models do not "
         "expose this table (verified empty on AF8.0.108 nsf-1050a-i).")

lld("Temperature sensor discovery", "sangfor.temp.discovery",
    "discovery[{#SNMPVALUE}," + TS + ".2]",
    [
     proto("Sensor {#SNMPVALUE}: Temperature", "sangfor.temp.value[{#SNMPINDEX}]",
           TS + ".3.{#SNMPINDEX}", "\u00b0C", desc="sfTempSensorReading.",
           tags=[("component", "hardware")]),
    ],
    desc="Temperature sensors from SANGFOR-MIB::sfTempSensorTable. Some NGAF "
         "models do not expose this table (verified empty on AF8.0.108 nsf-1050a-i).")

# ================= SNMP trap items =================
# Trap families the NGAF actually emits (confirmed from the device trap UI):
# sfGeneralTrap .1.3.6.1.4.1.35047.110.x (SANGFOR-MIB-COMPATIBLE.txt),
# sfFirewallTraps .1.3.6.1.4.1.35047.200.200.x (SANGFOR-MIB-AF.txt) and
# SNMPv2-MIB::warmStart (.1.3.6.1.6.3.1.1.5.2). Trap items route by the
# name regex in the key; the trap text becomes the item value.
#
# Recovery design (v0.2.0):
#  * Paired fail/normal traps share ONE item (common prefix regex). The
#    trigger is PROBLEM while the LAST received trap of the pair is the
#    failure and recovers as soon as the normal/recovery trap arrives.
#    Caveat: pairing is per trap-pair, not per interface index (trigger
#    expressions cannot compare varbinds).
#  * Unpaired problem traps recover after {$SANGFOR.TRAP_PROBLEM_HOURS} of
#    silence (most Sangfor alerts repeat while the condition holds -
#    verified live: attack traps re-sent every ~10 s).
#  * Pure informational events (config/rulebase/db updates, warm start)
#    carry NO trigger: the trap is stored as the item value (event-log
#    style); use Latest data or build custom triggers on top.

def trap_item(keyname, title, desc, trig=None):
    it = {
        "uuid": U("trap-" + keyname),
        "name": "SNMP trap: " + title,
        "type": "SNMP_TRAP",
        "key": "snmptrap[" + keyname + "]",
        "delay": "0",
        "history": "31d",
        "value_type": "TEXT",
        "description": desc,
        "tags": [{"tag": "component", "value": "trap"}],
    }
    if trig:
        it["triggers"] = [trig]
    items.append(it)

def _find(keyname, what):
    return 'find(/%s/snmptrap[%s],#1,"regexp","%s")=1' % (TPL, keyname, what)

for keyname, failn, normaln, title, desc in [
    ("sfFirewallTrapIf", "sfFirewallTrapIfFail", "sfFirewallTrapIfNormal",
     "Interface link failure",
     "Catches sfFirewallTrapIfFail (.35047.200.200.5) and "
     "sfFirewallTrapIfNormal (.200.200.4). PROBLEM while the last trap was "
     "the failure; recovers when the normal trap arrives."),
    ("sfLink", "sfLinkDownTrap", "sfLinkUpTrap", "Link failure alert",
     "Catches sfLinkDownTrap (.35047.110.24) and sfLinkUpTrap (.110.23). "
     "PROBLEM while the last trap was the failure; recovers when the link "
     "recovery trap arrives."),
]:
    trap_item(keyname, title, desc, trig={
        "uuid": U("trig-" + keyname),
        "expression": _find(keyname, failn),
        "recovery_mode": "RECOVERY_EXPRESSION",
        "recovery_expression": _find(keyname, normaln),
        "name": "Sangfor: " + title + " on {HOST.NAME}",
        "priority": "HIGH",
    })

for keyname, title, prio, desc in [
    ("sfFirewallTrapFwAttack", "Firewall under attack", "HIGH",
     "sfFirewallTrapFwAttack (.1.3.6.1.4.1.35047.200.200.6) - firewall itself under attack."),
    ("sfFirewallTrapNetworkAttack", "Protected network under attack", "HIGH",
     "sfFirewallTrapNetworkAttack (.1.3.6.1.4.1.35047.200.200.7) - protected network under attack."),
    ("sfFirewallTrapDualSwitch", "HA dual-active switch event", "HIGH",
     "sfFirewallTrapDualSwitch (.1.3.6.1.4.1.35047.200.200.2) - HA failover/dual switch occurred."),
    ("sfTemperatureWarnTrap", "Temperature alert", "HIGH",
     "sfTemperatureWarnTrap (.1.3.6.1.4.1.35047.110.1) - Temperature Alert."),
    ("sfCPUWarnTrap", "CPU alert", "WARNING",
     "sfCPUWarnTrap (.1.3.6.1.4.1.35047.110.2) - CPU Alert."),
    ("sfMemoryWarnTrap", "Memory alert", "WARNING",
     "sfMemoryWarnTrap (.1.3.6.1.4.1.35047.110.3) - Memory Alert."),
    ("sfDiskWarnTrap", "Hard disk alert", "HIGH",
     "sfDiskWarnTrap (.1.3.6.1.4.1.35047.110.4) - Hard Disk Alert."),
    ("sfPowerWarnTrap", "Power alert", "HIGH",
     "sfPowerWarnTrap (.1.3.6.1.4.1.35047.110.5) - Power Alert."),
    ("sfInterfaceDownTrap", "Interface alert", "HIGH",
     "sfInterfaceDownTrap (.1.3.6.1.4.1.35047.110.6) - Interface Alert."),
    ("sfFanWarnTrap", "Fan alert", "HIGH",
     "sfFanWarnTrap (.1.3.6.1.4.1.35047.110.7) - Fan Alert."),
    ("sfHAStatusTrap", "HA status alert", "HIGH",
     "sfHAStatusTrap (.1.3.6.1.4.1.35047.110.8) - HA Status Alert."),
    ("sfBypassChangeTrap", "Passthrough status alert", "WARNING",
     "sfBypassChangeTrap (.1.3.6.1.4.1.35047.110.19) - Passthrough Status Alert (bypass mode change)."),
    ("sfPortResourceWarnTrap", "Insufficient port resources", "WARNING",
     "sfPortResourceWarnTrap (.1.3.6.1.4.1.35047.110.25) - Insufficient Port Resources."),
    ("sfSLATrap", "SLA-based link failover", "WARNING",
     "sfSLATrap (.1.3.6.1.4.1.35047.110.27) - SLA-based Link Failover."),
]:
    trap_item(keyname, title, desc, trig={
        "uuid": U("trig-" + keyname),
        "expression": (_find(keyname, keyname) +
                       " and nodata(/%s/snmptrap[%s],{$SANGFOR.TRAP_PROBLEM_HOURS})=0"
                       % (TPL, keyname)),
        "recovery_mode": "RECOVERY_EXPRESSION",
        "recovery_expression":
            "nodata(/%s/snmptrap[%s],{$SANGFOR.TRAP_PROBLEM_HOURS})=1" % (TPL, keyname),
        "name": "Sangfor: " + title + " on {HOST.NAME}",
        "priority": prio,
    })

for keyname, title, desc in [
    ("sfFirewallTrapConfChange", "Configuration changed (event log)",
     "sfFirewallTrapConfChange (.1.3.6.1.4.1.35047.200.200.1) - NGAF configuration was updated. Event-log item: no trigger."),
    ("sfFirewallRulebaseUpdate", "Security rulebase updated (event log)",
     "sfFirewallRulebaseUpdate (.1.3.6.1.4.1.35047.200.200.3) - firewall rules were updated. Event-log item: no trigger."),
    ("sfRuleBaseUpgradeTrap", "Database update (event log)",
     "sfRuleBaseUpgradeTrap (.1.3.6.1.4.1.35047.110.17) - Database Update Alert. Event-log item: no trigger."),
    ("warmStart", "Device warm start (event log)",
     "SNMPv2-MIB::warmStart (.1.3.6.1.6.3.1.1.5.2) - Warm Start Alert. Event-log item: no trigger."),
]:
    trap_item(keyname, title, desc)

# NOTE: no snmptrap.fallback was previously omitted because the standard
# "Network Generic Device by SNMP" template ships one. Per Eddie's request this
# template now REPLACES it, so the fallback (and the useful generic items:
# ICMP, system info, uptimes, snmp availability) are ported below.

# ---- ported from "Network Generic Device by SNMP" (template 10226) ----
def plain_item(name, key, itype, vtype="FLOAT", units="", desc="", delay=None,
               pre=None, trig=None, tags=()):
    it = {"uuid": U("item-" + key), "name": name, "type": itype, "key": key,
          "delay": delay or "{$SANGFOR.UPDATE.FREQ}", "history": "7d",
          "value_type": vtype, "description": desc}
    if units:
        it["units"] = units
    if pre:
        it["preprocessing"] = pre
    if tags:
        it["tags"] = [{"tag": a, "value": b} for a, b in tags]
    if trig:
        it["triggers"] = [trig]
    items.append(it)
    return it

ICMP_TAGS = [("component", "icmp")]

plain_item("ICMP ping", "icmpping", "SIMPLE", "UNSIGNED",
           desc="ICMP availability check (Simple check; ported from the "
                "generic SNMP template). See the paired trigger for the "
                "up/down logic.",
           tags=ICMP_TAGS,
           trig=TR("HIGH", "max(/%s/icmpping,#3)=0" % TPL,
                   "Device unavailable by ICMP ping on {HOST.NAME}"))
plain_item("ICMP loss", "icmppingloss", "SIMPLE", "FLOAT", "%",
           desc="Packet loss (%) per ICMP check (fping defaults; tune via "
                "the FpingLocation system setup, not per-item macros). "
                "Ported from generic SNMP template.",
           tags=ICMP_TAGS,
           trig=TR("WARNING",
                   "min(/%s/icmppingloss,{$ICMP_LOSS_MIN_OCCURRENCES})>{$ICMP_LOSS_WARN}"
                   " and max(/%s/icmppingloss,#3)<100" % (TPL, TPL),
                   "High ICMP ping loss on {HOST.NAME}"))
plain_item("ICMP response time", "icmppingsec", "SIMPLE", "FLOAT", "s",
           desc="Average ICMP response time in seconds (ported).",
           tags=ICMP_TAGS,
           trig=TR("WARNING",
                   "avg(/%s/icmppingsec,15m)>{$ICMP_RESPONSE_TIME_WARN}" % TPL,
                   "High ICMP ping response time on {HOST.NAME}"))

plain_item("SNMP agent availability", "zabbix[host,snmp,available]",
           "INTERNAL", "UNSIGNED",
           desc="Status of SNMP agent availability. 1 - available, 0 - not "
                "available (ported from generic SNMP template).",
           tags=[("component", "snmp")],
           trig=TR("WARNING", "last(/%s/zabbix[host,snmp,available])=0" % TPL,
                   "No SNMP data collection from {HOST.NAME}"))

SYS15M = ["{$SANGFOR.INFO.FREQ}"]
for nm, ky, oid, ds in [
    ("System contact details", "system.contact[sysContact.0]",
     "1.3.6.1.2.1.1.4.0", "The contact person responsible for this device (RFC1213-MIB::sysContact)."),
    ("System description", "system.descr[sysDescr.0]",
     "1.3.6.1.2.1.1.1.0", "Full description of the device (RFC1213-MIB::sysDescr)."),
    ("System location", "system.location[sysLocation.0]",
     "1.3.6.1.2.1.1.6.0", "Physical location (RFC1213-MIB::sysLocation)."),
    ("System name", "system.name",
     "1.3.6.1.2.1.1.5.0", "Name of this device, as set on the device itself (RFC1213-MIB::sysName)."),
    ("System object ID", "system.objectid[sysObjectID.0]",
     "1.3.6.1.2.1.1.2.0", "Vendor's identification of this device (RFC1213-MIB::sysObjectID)."),
]:
    plain_item(nm, ky, "SNMP_AGENT", "CHAR", desc=ds + " Ported from generic "
               "SNMP template.", delay=SYS15M[0], tags=[("component", "system")],
               trig=None)
    items[-1]["snmp_oid"] = "get[" + oid + "]"

plain_item("Uptime (network)", "system.net.uptime[sysUpTime.0]", "SNMP_AGENT",
           "FLOAT", "uptime",
           desc="Time since the network management portion of the system was "
                "last re-initialized (RFC1213-MIB::sysUpTime, timeticks -> s). "
                "Ported.", delay="30s", pre=[P("MULTIPLIER", "0.01")],
           tags=[("component", "system")])
items[-1]["snmp_oid"] = "get[1.3.6.1.2.1.1.3.0]"
plain_item("Uptime (hardware)", "system.hw.uptime[hrSystemUptime.0]",
           "SNMP_AGENT", "FLOAT", "uptime",
           desc="Time since the whole system was last re-initialized "
                "(HOST-RESOURCES-MIB::hrSystemUptime, timeticks -> s). Ported.",
           delay="30s", pre=[P("MULTIPLIER", "0.01")],
           tags=[("component", "system")])
items[-1]["snmp_oid"] = "get[1.3.6.1.2.1.25.1.1.0]"

# restart + rename triggers (attached to uptime/name items)
for it in items:
    if it["key"] == "system.net.uptime[sysUpTime.0]":
        it["triggers"] = [{
            "uuid": U("trig-restart"),
            "expression": ("change(/%s/system.net.uptime[sysUpTime.0])<0 and "
                           "change(/%s/system.hw.uptime[hrSystemUptime.0])<0"
                           % (TPL, TPL)),
            "recovery_mode": "RECOVERY_EXPRESSION",
            "recovery_expression": "nodata(/%s/system.net.uptime[sysUpTime.0],10m)=0" % TPL,
            "name": "{HOST.NAME} has been restarted",
            "event_name": "{HOST.NAME} has been restarted",
            "priority": "WARNING",
        }]
    if it["key"] == "system.name":
        it["triggers"] = [{
            "uuid": U("trig-namechg"),
            "expression": ("change(/%s/system.name)<>0 and "
                           "length(last(/%s/system.name))>0" % (TPL, TPL)),
            "recovery_mode": "RECOVERY_EXPRESSION",
            "recovery_expression": "nodata(/%s/system.name,1d)=1" % TPL,
            "name": "System name has changed (new name: {ITEM.LASTVALUE1})",
            "priority": "INFO",
        }]
    if it["key"] == "zabbix[host,snmp,available]":
        # 8.0 JSON import: dependency "name" must be the BARE trigger name
        # (no template prefix). On the very first import into an empty DB the
        # referenced trigger may not exist yet and the import aborts with
        # "...which does not exist" — simply run the same import a second
        # time and it resolves. (Verified 2026-11-16.)
        it["triggers"][0]["dependencies"] = [{
            "name": "Device unavailable by ICMP ping on {HOST.NAME}",
            "expression": "max(/%s/icmpping,#3)=0" % TPL}]

items.append({
    "uuid": U("trap-fallback"),
    "name": "SNMP trap: catch-all (unmatched)",
    "type": "SNMP_TRAP",
    "key": "snmptrap.fallback",
    "delay": "0",
    "history": "31d",
    "value_type": "TEXT",
    "description": "Catches any SNMP trap not matched by a named snmptrap[] "
                   "item. Ported from Network Generic Device by SNMP; this "
                   "template is standalone, do NOT link it together with that "
                   "template (duplicate fallback key).",
    "tags": [{"tag": "component", "value": "trap"}],
})

# ================= macros =================
for m, v, d in [
    ("{$SANGFOR.UPDATE.FREQ}", "1m", "Update interval for metrics."),
    ("{$SANGFOR.DISCOVERY.FREQ}", "1h", "Low-level discovery interval."),
    ("{$SANGFOR.CPU.MAX}", "90", "CPU utilization (%) warning threshold."),
    ("{$SANGFOR.CPU_CORE.MAX}", "95", "Per-core CPU utilization (%) threshold."),
    ("{$SANGFOR.MEM.MAX}", "90", "Memory usage (%) warning threshold."),
    ("{$SANGFOR.DISK.MAX}", "85", "Filesystem usage (%) warning threshold."),
    ("{$SANGFOR.DISK_TEMP.MAX}", "70", "Disk temperature (C) warning threshold."),
    ("{$SANGFOR.IF_DROP.MAX}", "1000",
     "Interface discard rate (drops/s) warning threshold."),
    ("{$SANGFOR.TRAP_PROBLEM_HOURS}", "4h",
     "Auto-recovery window for unpaired trap problems: the problem clears "
     "this long after the LAST matching trap (Sangfor repeats active "
     "alerts)."),
    ("{$SANGFOR.INFO.FREQ}", "15m",
     "Update interval for system info items (ported from generic template)."),
    ("{$ICMP_LOSS_WARN}", "20",
     "Packet loss (%) that triggers a warning."),
    ("{$ICMP_LOSS_MIN_OCCURRENCES}", "3",
     "How many times in a row the loss must be above the warning threshold to "
     "trigger."),
    ("{$ICMP_RESPONSE_TIME_WARN}", "0.15",
     "Average response time (s) that triggers a warning."),
]:
    macros.append({"macro": m, "value": v, "description": d})

# ================= assemble =================
tpl = {"uuid": U("template"), "template": TPL, "name": TPL,
       "description": "Sangfor NGAF monitoring via private SANGFOR-MIB "
                      "(enterprises %s). Requires SNMP v2c or later; "
                      "community/v3 credentials are configured on the host "
                      "SNMP interface (8.0 items have no community field). "
                      "Verified against a "
                      "live NGAF running AF8.0.108.657 (nsf-1050a-i): "
                      "sfIfInRate/sfIfOutRate are instantaneous byte/s gauges "
                      "(x8 only, no Change per second); sfIfInPkts/sfIfOutPkts/"
                      "drops are cumulative counters (Change per second); "
                      "memory ints are kB; disk ints are MB; sfSysDiskUsage "
                      "(.52.1) is not implemented on AF 8.0 and is NOT polled; "
                      "fan/PSU/temp tables may be empty on some models."
                      % BASE,
       "groups": [{"name": TGROUP}],
       "items": items,
       "discovery_rules": drs,
       "macros": macros}

doc = {"zabbix_export": {
    "version": "8.0",
    "template_groups": [{"uuid": U("group"), "name": TGROUP}],
    "templates": [tpl]}}

_here = Path(__file__).resolve().parent
out = (_here.parent if _here.name == "scripts" else _here) / "template_sangfor_ngaf_snmp.json"
with out.open("w", encoding="utf-8") as f:
    json.dump(doc, f, indent=2, ensure_ascii=False)
print("written", out)
print("items:", len(items), "lld:", len(drs))
