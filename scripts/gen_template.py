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
              trig=None, tags=(), history="7d", delay=None, valuemap=None):
    it = {"uuid": U("item-" + key), "name": name, "type": "SNMP_AGENT", "snmp_oid": oid,
          "key": key, "delay": delay or "{$SANGFOR.UPDATE.FREQ}",
          "history": history, "value_type": vtype, "description": desc}
    if vtype in ("FLOAT", "UNSIGNED"):
        it["trends"] = "90d" if any(s in key for s in (".bps", ".pps", ".drop")) else "365d"
    if units:
        it["units"] = units
    if pre:
        it["preprocessing"] = pre
    if tags:
        it["tags"] = [{"tag": a, "value": b} for a, b in tags]
    if valuemap:
        it["valuemap"] = {"name": valuemap}
    if trig:
        it["triggers"] = [trig]
    items.append(it)
    return it

def TR(prio, expr, name):
    return {"uuid": U("trig-" + name), "expression": expr, "name": name,
            "priority": prio}

def TRH(prio, expr, name, rec):
    # threshold trigger with hysteresis: recover only below a lower band so
    # values hovering at the threshold do not flap problem/recovery.
    return {"uuid": U("trig-" + name), "expression": expr, "name": name,
            "priority": prio, "recovery_mode": "RECOVERY_EXPRESSION",
            "recovery_expression": rec}

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
# Discrete-state items rarely change; discard duplicates, keep a 1h
# heartbeat. Safe with last()-based triggers. NEVER apply to trap items
# (breaks nodata() recovery), uptime (change()) or system.name (#1<>#2).
DCH = P("DISCARD_UNCHANGED_HEARTBEAT", "1h")
JSNUM = [P("JAVASCRIPT",
      "var n = value.replace(/[^0-9.]/g, '');"
      "if (n === '' || isNaN(parseFloat(n))) { throw 'non-numeric: ' + value; }"
      " return n;")]

# ================= scalar items =================
snmp_item("Sangfor: Device description", "sangfor.device.descr",
          "get[" + GEN + ".1.0]", "CHAR",
          desc="sfDeviceDescr.", delay="{$SANGFOR.INFO.FREQ}")
snmp_item("Sangfor: Device name", "sangfor.device.name",
          "get[" + GEN + ".17.0]", "CHAR",
          desc="sfSysDevName.", delay="{$SANGFOR.INFO.FREQ}")
snmp_item("Sangfor: Software version", "sangfor.software.version",
          "get[" + GEN + ".18.0]", "CHAR",
          desc="sfSysSoftVersion.", delay="{$SANGFOR.INFO.FREQ}")
snmp_item("Sangfor: AF version", "sangfor.af.version",
          "get[" + GEN + ".24.0]", "CHAR",
          desc="afSysSoftVersion.", delay="{$SANGFOR.INFO.FREQ}")
_serial = snmp_item("Sangfor: Serial number", "sangfor.serial.number",
          "get[" + GEN + ".40.0]", "CHAR",
          desc="sfSnGW - serial number of the appliance. Not implemented on "
               "AF8.0.108 (nsf-1050a-i): item ships DISABLED to avoid "
               "unsupported-noise; enable it if your model exposes sfSnGW.",
               delay="{$SANGFOR.INFO.FREQ}")
_serial["status"] = "DISABLED"

snmp_item("Sangfor: Device status", "sangfor.device.status",
          "get[" + GEN + ".12.0]",
          desc="sfDeviceStatus: 0 - Warning, 1 - Normal.", pre=[DCH],
          tags=[("component", "health")], valuemap="Sangfor: device status",
          trig=TR("WARNING", "last(/%s/sangfor.device.status)=0" % TPL,
                  "Sangfor: Device reports WARNING status on {HOST.NAME}"))

snmp_item("Sangfor: CPU utilization (30s)", "sangfor.cpu.util.30s",
          "get[" + GEN + ".19.4.0]", units="%",
          desc="sfCpuAllCostRateLast30Sec.", tags=[("component", "cpu")])
snmp_item("Sangfor: CPU utilization (1 min)", "sangfor.cpu.util.1m",
          "get[" + GEN + ".19.5.0]", units="%",
          desc="sfCpuAllCostRateLast1Min.", tags=[("component", "cpu")],
          trig=TRH("AVERAGE",
                  "last(/%s/sangfor.cpu.util.1m)>{$SANGFOR.CPU.MAX}" % TPL,
                  "Sangfor: High CPU utilization over {$SANGFOR.CPU.MAX}% on {HOST.NAME}",
                  "last(/%s/sangfor.cpu.util.1m)<{$SANGFOR.CPU.MAX}*0.9" % TPL))
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
          trig=TRH("AVERAGE",
                  "last(/%s/sangfor.mem.util)>{$SANGFOR.MEM.MAX}" % TPL,
                  "Sangfor: High memory usage over {$SANGFOR.MEM.MAX}% on {HOST.NAME}",
                  "last(/%s/sangfor.mem.util)<{$SANGFOR.MEM.MAX}*0.9" % TPL))
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
          desc="sfHAEnable: 0 - disabled, 1 - enabled.", pre=[DCH],
          tags=[("component", "ha")], history="31d",
          valuemap="Sangfor: HA enable")
snmp_item("Sangfor: HA mode", "sangfor.ha.mode",
          "get[" + GEN + ".64.2.0]",
          desc="sfHAMode: 0 - invalid, 1 - master-master, 2 - master-slave, "
               "3 - mirror.", pre=[DCH],
               tags=[("component", "ha")], history="31d",
               valuemap="Sangfor: HA mode")
snmp_item("Sangfor: HA current status", "sangfor.ha.status",
          "get[" + GEN + ".64.3.0]",
          desc="sfHACurStatus: 0 - invalid, 1 - init, 4 - master, 5 - slave.",
          pre=[DCH], tags=[("component", "ha")], valuemap="Sangfor: HA status")
snmp_item("Sangfor: HA control link status", "sangfor.ha.ctrllink",
          "get[" + GEN + ".64.6.0]",
          desc="sfHACtrlLinkStatus: 0 - invalid, 1 - normal, 2 - abnormal.",
          pre=[DCH], tags=[("component", "ha")],
          trig=TR("HIGH", "last(/%s/sangfor.ha.ctrllink)=2" % TPL,
                  "Sangfor: HA control link ABNORMAL on {HOST.NAME}"))
snmp_item("Sangfor: HA data link status", "sangfor.ha.datalink",
          "get[" + GEN + ".64.7.0]",
          desc="sfHADataLinkStatus: 0 - invalid, 1 - normal, 2 - abnormal.",
          pre=[DCH], tags=[("component", "ha")],
          trig=TR("HIGH", "last(/%s/sangfor.ha.datalink)=2" % TPL,
                  "Sangfor: HA data link ABNORMAL on {HOST.NAME}"))
snmp_item("Sangfor: HA sync state", "sangfor.ha.sync",
          "get[" + GEN + ".64.8.0]",
          desc="sfHASyncState: 0 - invalid, 1 - sync running, 2 - sync end, "
               "3 - unknown.", pre=[DCH], tags=[("component", "ha")],
               valuemap="Sangfor: HA sync state")

# ================= LLD =================
IF = GEN + ".34.1"    # sfIfTable
DK = GEN + ".5.1"     # sfDiskTable
CC = GEN + ".20.1"    # sfCpuCostRateTable
FN = GEN + ".14.1"    # sfSysFanTable
PW = GEN + ".15.1"    # sfSysPowerTable
TS = GEN + ".59.1"    # sfTempSensorTable

def proto(name, key, oid, units="", pre=None, vtype="FLOAT", desc="",
          tags=(), trig=None, valuemap=None):
    it = {"uuid": U("proto-" + key), "name": name, "type": "SNMP_AGENT",
          "snmp_oid": "get[" + oid + "]", "key": key,
          "delay": "{$SANGFOR.UPDATE.FREQ}",
          "history": "7d", "value_type": vtype, "description": desc}
    if vtype in ("FLOAT", "UNSIGNED"):
        it["trends"] = "90d" if any(s in key for s in (".bps", ".pps", ".drop")) else "365d"
    if units:
        it["units"] = units
    if pre:
        it["preprocessing"] = pre
    if tags:
        it["tags"] = [{"tag": a, "value": b} for a, b in tags]
    if valuemap:
        it["valuemap"] = {"name": valuemap}
    if trig:
        it["_trig"] = trig
    return it

def lld(name, key, disc_oid, protos, desc="", filter=None):
    dr = {"uuid": U("lld-" + key), "name": name, "type": "SNMP_AGENT",
          "snmp_oid": disc_oid, "key": key,
          "delay": "{$SANGFOR.DISCOVERY.FREQ}",
          # lost resources: disable immediately, delete after 30d (keeps
          # history of vanished interfaces longer than the 7d default)
          "lifetime": "30d",
          "enabled_lifetime": "0",
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
     proto("Interface {#SNMPVALUE}: Operational status",
           "sangfor.if.operstatus[{#SNMPINDEX}]",
           "1.3.6.1.2.1.2.2.1.8.{#SNMPINDEX}",
           desc="IF-MIB::ifOperStatus - authoritative per-interface link "
                "state (verified exposed on AF8.0.108; indexes match "
                "sfIfTable).", pre=[DCH],
           tags=[("component", "network")], valuemap="Sangfor: if oper status"),
     proto("Interface {#SNMPVALUE}: Admin status",
           "sangfor.if.adminstatus[{#SNMPINDEX}]",
           "1.3.6.1.2.1.2.2.1.7.{#SNMPINDEX}",
           desc="IF-MIB::ifAdminStatus - used to suppress link-down alerts "
                "on administratively disabled ports.", pre=[DCH],
           tags=[("component", "network")], valuemap="Sangfor: if admin status",
           trig=TR("HIGH",
                   "last(/%s/sangfor.if.operstatus[{#SNMPINDEX}])=2"
                   " and last(/%s/sangfor.if.adminstatus[{#SNMPINDEX}])=1"
                   " and {$SANGFOR.IF.LINK.ALERT:\"{#SNMPVALUE}\"}=1" % (TPL, TPL),
                   "Interface {#SNMPVALUE}: link down on {HOST.NAME}")),
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
           trig=TRH("WARNING",
                   "last(/%s/sangfor.disk.pused[{#SNMPINDEX}])>{$SANGFOR.DISK.MAX}" % TPL,
                   "Disk {#SNMPVALUE}: space usage over {$SANGFOR.DISK.MAX}% on {HOST.NAME}",
                   "last(/%s/sangfor.disk.pused[{#SNMPINDEX}])<{$SANGFOR.DISK.MAX}*0.9" % TPL)),
     proto("Disk {#SNMPVALUE}: Temperature", "sangfor.disk.temp[{#SNMPINDEX}]",
           DK + ".10.{#SNMPINDEX}", "\u00b0C",
           desc="sfDiskTemp.", tags=[("component", "disk")],
           trig=TRH("WARNING",
                   "last(/%s/sangfor.disk.temp[{#SNMPINDEX}])>{$SANGFOR.DISK_TEMP.MAX}" % TPL,
                   "Disk {#SNMPVALUE}: high temperature ({ITEM.LASTVALUE1}) on {HOST.NAME}",
                   "last(/%s/sangfor.disk.temp[{#SNMPINDEX}])<{$SANGFOR.DISK_TEMP.MAX}-5" % TPL)),
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
           trig=TRH("WARNING",
                   "last(/%s/sangfor.cpu.util[{#SNMPINDEX}])>{$SANGFOR.CPU_CORE.MAX}" % TPL,
                   "CPU core {#SNMPVALUE}: utilization over {$SANGFOR.CPU_CORE.MAX}% on {HOST.NAME}",
                   "last(/%s/sangfor.cpu.util[{#SNMPINDEX}])<{$SANGFOR.CPU_CORE.MAX}*0.9" % TPL)),
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
           pre=[DCH], tags=[("component", "hardware")], valuemap="Sangfor: hw state",
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
           pre=[DCH], tags=[("component", "hardware")], valuemap="Sangfor: hw state",
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

TRAP_AF = "SANGFOR-AF-MIB"      # 35047.200.200.x family (SANGFOR-MIB-AF.txt)
TRAP_SF = "SANGFOR-MIB"         # 35047.110.x family (SANGFOR-MIB-COMPATIBLE.txt)
TRAP_STD = "SNMPv2-MIB"         # warmStart / coldStart
# Route traps ONLY on the snmpTrapOID varbind line: an unanchored trap name
# would also match payload text (interface names, descriptions) and, since
# a trap is copied into EVERY matching item, double-route it. \s keeps
# literal spaces out of item keys.
ANCHOR = "snmpTrapOID\\.0\\s=\\s%s::%s"

def trap_keyre(pairs):
    return "|".join(ANCHOR % (m, n) for m, n in pairs)

def trap_item(keyname, title, desc, trig=None, mibs=None):
    it = {
        "uuid": U("trap-" + keyname),
        "name": "SNMP trap: " + title,
        "type": "SNMP_TRAP",
        "key": "snmptrap[" + trap_keyre(mibs or [(TRAP_SF, keyname)]) + "]",
        "delay": "0",
        "history": "31d",
        "value_type": "LOG",
        "description": desc,
        "tags": [{"tag": "component", "value": "trap"}],
    }
    if trig:
        it["triggers"] = [trig]
    items.append(it)

def _find(keyre, what):
    return 'find(/%s/snmptrap[%s],#1,"regexp","%s")=1' % (TPL, keyre, what)

# v0.5.0: link fail/normal traps are EVENT-LOG items (no trigger). The MIB
# defines no varbinds for them and real samples carry no interface
# identifier, so per-trap-pair triggers could not track per-interface state
# (WAN1 up would clear WAN2's problem). Authoritative per-interface link
# alerting is done by polling IF-MIB ifOperStatus/ifAdminStatus in the
# interface LLD instead; these items keep the instant trap record.
for keyname, mod, failn, normaln, title, desc in [
    ("sfFirewallTrapIf", TRAP_AF, "sfFirewallTrapIfFail", "sfFirewallTrapIfNormal",
     "Interface link fail/normal (event log)",
     "Catches sfFirewallTrapIfFail (.35047.200.200.5) and "
     "sfFirewallTrapIfNormal (.200.200.4). Event-log item: no trigger - "
     "per-interface link alerting uses ifOperStatus polling."),
    ("sfLink", TRAP_SF, "sfLinkDownTrap", "sfLinkUpTrap",
     "Link down/up (event log)",
     "Catches sfLinkDownTrap (.35047.110.24) and sfLinkUpTrap (.110.23). "
     "Event-log item: no trigger - per-interface link alerting uses "
     "ifOperStatus polling."),
]:
    trap_item(keyname, title, desc, mibs=[(mod, failn), (mod, normaln)])

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
    mod = TRAP_AF if keyname.startswith("sfFirewallTrap") else TRAP_SF
    anch = ANCHOR % (mod, keyname)
    trap_item(keyname, title, desc, mibs=[(mod, keyname)], trig={
        "uuid": U("trig-" + keyname),
        "expression": (_find(anch, anch) +
                       " and nodata(/%s/snmptrap[%s],{$SANGFOR.TRAP_PROBLEM_HOURS})=0"
                       % (TPL, anch)),
        "recovery_mode": "RECOVERY_EXPRESSION",
        # Recover ONLY when traps went silent but SNMP polling still works.
        # Silence + dead polling = collector/network outage, NOT a resolved
        # attack - keep the problem open until data collection proves alive.
        "recovery_expression": (
            "nodata(/%s/snmptrap[%s],{$SANGFOR.TRAP_PROBLEM_HOURS})=1"
            " and last(/%s/zabbix[host,snmp,available])=1" % (TPL, anch, TPL)),
        "name": "Sangfor: " + title + " on {HOST.NAME}",
        "priority": prio,
    })

for mod, keyname, title, desc in [
    (TRAP_AF, "sfFirewallTrapConfChange", "Configuration changed (event log)",
     "sfFirewallTrapConfChange (.1.3.6.1.4.1.35047.200.200.1) - NGAF configuration was updated. Event-log item: no trigger."),
    (TRAP_AF, "sfFirewallRulebaseUpdate", "Security rulebase updated (event log)",
     "sfFirewallRulebaseUpdate (.1.3.6.1.4.1.35047.200.200.3) - firewall rules were updated. Event-log item: no trigger."),
    (TRAP_SF, "sfRuleBaseUpgradeTrap", "Database update (event log)",
     "sfRuleBaseUpgradeTrap (.1.3.6.1.4.1.35047.110.17) - Database Update Alert. Event-log item: no trigger."),
    (TRAP_STD, "warmStart", "Device warm start (event log)",
     "SNMPv2-MIB::warmStart (.1.3.6.1.6.3.1.1.5.2) - Warm Start Alert. Event-log item: no trigger."),
    (TRAP_STD, "coldStart", "Device cold start (event log)",
     "SNMPv2-MIB::coldStart (.1.3.6.1.6.3.1.1.5.1) - full restart; not in the NGAF trap UI list but may be sent. Event-log item: no trigger."),
]:
    trap_item(keyname, title, desc, mibs=[(mod, keyname)])

# NOTE: no snmptrap.fallback was previously omitted because the standard
# "Network Generic Device by SNMP" template ships one. Per Eddie's request this
# template now REPLACES it, so the fallback (and the useful generic items:
# ICMP, system info, uptimes, snmp availability) are ported below.

# ---- ported from "Network Generic Device by SNMP" (template 10226) ----
def plain_item(name, key, itype, vtype="FLOAT", units="", desc="", delay=None,
               pre=None, trig=None, tags=(), oid=None):
    it = {"uuid": U("item-" + key), "name": name, "type": itype, "key": key,
          "delay": delay or "{$SANGFOR.UPDATE.FREQ}", "history": "7d",
          "value_type": vtype, "description": desc}
    if vtype in ("FLOAT", "UNSIGNED"):
        it["trends"] = "365d"
    if oid:
        it["snmp_oid"] = "get[" + oid + "]"
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
                   "min(/%s/icmppingloss,5m)>{$ICMP_LOSS_WARN}"
                   " and min(/%s/icmppingloss,5m)<100" % (TPL, TPL),
                   "High ICMP ping loss on {HOST.NAME}"))
plain_item("ICMP response time", "icmppingsec", "SIMPLE", "FLOAT", "s",
           desc="Average ICMP response time in seconds (ported).",
           tags=ICMP_TAGS,
           trig=TR("WARNING",
                   "avg(/%s/icmppingsec,5m)>{$ICMP_RESPONSE_TIME_WARN}" % TPL,
                   "High ICMP ping response time on {HOST.NAME}"))

plain_item("SNMP agent availability", "zabbix[host,snmp,available]",
           "INTERNAL", "UNSIGNED",
           desc="Status of SNMP agent availability. 1 - available, 0 - not "
                "available (ported from generic SNMP template).",
           tags=[("component", "snmp")],
           trig=TR("WARNING",
                   "max(/%s/zabbix[host,snmp,available],{$SNMP.TIMEOUT})=0" % TPL,
                   "No SNMP data collection from {HOST.NAME}"))

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
               "SNMP template.", delay="{$SANGFOR.INFO.FREQ}",
               tags=[("component", "system")], oid=oid)

plain_item("Uptime (network)", "system.net.uptime[sysUpTime.0]", "SNMP_AGENT",
           "FLOAT", "uptime",
           desc="Time since the network management portion of the system was "
                "last re-initialized (RFC1213-MIB::sysUpTime, timeticks -> s). "
                "Ported.", delay="30s", pre=[P("MULTIPLIER", "0.01")],
           tags=[("component", "system")], oid="1.3.6.1.2.1.1.3.0")
plain_item("Uptime (hardware)", "system.hw.uptime[hrSystemUptime.0]",
           "SNMP_AGENT", "FLOAT", "uptime",
           desc="Time since the whole system was last re-initialized "
                "(HOST-RESOURCES-MIB::hrSystemUptime, timeticks -> s). Ported.",
           delay="30s", pre=[P("MULTIPLIER", "0.01")],
           tags=[("component", "system")], oid="1.3.6.1.2.1.25.1.1.0")

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
            "dependencies": [{
                "name": "No SNMP data collection from {HOST.NAME}",
                "expression":
                    "max(/%s/zabbix[host,snmp,available],{$SNMP.TIMEOUT})=0"
                    % TPL}],
        }]
    if it["key"] == "system.name":
        it["triggers"] = [{
            "uuid": U("trig-namechg"),
            "expression": ("last(/%s/system.name,#1)<>last(/%s/system.name,#2)"
                           " and length(last(/%s/system.name))>0"
                           % (TPL, TPL, TPL)),
            "event_name": "System name has changed (new name: {ITEM.VALUE})",
            "description": "The name of the system has changed. Acknowledge "
                           "to close the problem manually.",
            "name": "System name has changed (new name: {ITEM.LASTVALUE1})",
            "priority": "INFO",
            "manual_close": "YES",
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
    if it["key"] == "icmppingloss":
        it["triggers"][0]["dependencies"] = [{
            "name": "Device unavailable by ICMP ping on {HOST.NAME}",
            "expression": "max(/%s/icmpping,#3)=0" % TPL}]
    if it["key"] == "icmppingsec":
        it["triggers"][0]["dependencies"] = [
            {"name": "High ICMP ping loss on {HOST.NAME}",
             "expression": "min(/%s/icmppingloss,5m)>{$ICMP_LOSS_WARN}"
                           " and min(/%s/icmppingloss,5m)<100" % (TPL, TPL)},
            {"name": "Device unavailable by ICMP ping on {HOST.NAME}",
             "expression": "max(/%s/icmpping,#3)=0" % TPL}]

items.append({
    "uuid": U("trap-fallback"),
    "name": "SNMP trap: catch-all (unmatched)",
    "type": "SNMP_TRAP",
    "key": "snmptrap.fallback",
    "delay": "0",
    "history": "31d",
    "value_type": "LOG",
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
    ("{$SANGFOR.IF.LINK.ALERT}", "0",
     "Per-interface link-down alerting is OPT-IN: set this macro to 1 with "
     "the interface name as context on critical ports, e.g. "
     "{$SANGFOR.IF.LINK.ALERT:\"eth1\"} = 1. Default 0 because unused but "
     "admin-enabled ports would otherwise alert."),
    ("{$SNMP.TIMEOUT}", "5m",
     "How long SNMP polling must be down before 'No SNMP data collection' "
     "fires (ported from the generic template)."),
    ("{$ICMP_RESPONSE_TIME_WARN}", "0.15",
     "Average response time (s) that triggers a warning."),
]:
    macros.append({"macro": m, "value": v, "description": d})

# ================= graphs =================
def gitem(key, color, dt=None, ys=None, so=0):
    # NOTE: omit drawtype for plain LINE - the 8.0 JSON importer rejects the
    # literal "LINE" constant (only non-default drawtypes are written).
    gi = {"color": color, "sortorder": str(so),
          "item": {"host": TPL, "key": key}}
    if dt:
        gi["drawtype"] = dt
    if ys:
        gi["yaxisside"] = ys
    return gi

def graph(name, gitems):
    return {"uuid": U("graph-" + name), "name": name, "graph_items": gitems}

graphs = [
    graph("Sangfor NGAF: CPU utilization", [
        gitem("sangfor.cpu.util.30s", "00C800", "GRADIENT_LINE", so=0),
        gitem("sangfor.cpu.util.1m", "FF3333", "BOLD_LINE", so=1),
        gitem("sangfor.cpu.util.5m", "0000FF", so=2)]),
    graph("Sangfor NGAF: Memory", [
        gitem("sangfor.mem.total", "00AA00", so=0),
        gitem("sangfor.mem.free", "AAAAAA", "DASHED_LINE", so=1),
        gitem("sangfor.mem.util", "FF00FF", "BOLD_LINE", ys="RIGHT", so=2)]),
    graph("Sangfor NGAF: Sessions", [
        gitem("sangfor.sessions.current", "3333FF", "GRADIENT_LINE", so=0),
        gitem("sangfor.sessions.new.persec", "FF6600", so=1,
              ys="RIGHT")]),
    graph("Sangfor NGAF: Throughput", [
        gitem("sangfor.throughput.in", "00C800", "GRADIENT_LINE", so=0),
        gitem("sangfor.throughput.out", "FF3333", "BOLD_LINE", so=1)]),
]

# graph prototypes on the interface discovery (per-interface WAN traffic)
next(d for d in drs if d["key"] == "sangfor.if.discovery")["graph_prototypes"] = [
    graph("Interface {#SNMPVALUE}: Traffic", [
        gitem("sangfor.if.in.bps[{#SNMPINDEX}]", "199C0D", "GRADIENT_LINE", so=0),
        gitem("sangfor.if.out.bps[{#SNMPINDEX}]", "F63100", "BOLD_LINE", so=1)]),
    graph("Interface {#SNMPVALUE}: Discards", [
        gitem("sangfor.if.in.drop[{#SNMPINDEX}]", "FF4646", so=0),
        gitem("sangfor.if.out.drop[{#SNMPINDEX}]", "005500", so=1)]),
]

# ================= dashboard =================
def w_item(key, name, x, y, w=18, h=2, show="2"):
    return {"type": "item", "name": name, "x": str(x), "y": str(y),
            "width": str(w), "height": str(h),
            "fields": [
                {"type": "ITEM", "name": "itemid.0",
                 "value": {"host": TPL, "key": key}},
                {"type": "INTEGER", "name": "show.0", "value": show}]}

def w_gauge(key, name, x, y, w=8, h=3):
    return {"type": "gauge", "name": name, "x": str(x), "y": str(y),
            "width": str(w), "height": str(h),
            "fields": [
                {"type": "ITEM", "name": "itemid.0",
                 "value": {"host": TPL, "key": key}},
                {"type": "STRING", "name": "min", "value": "0"},
                {"type": "STRING", "name": "max", "value": "100"},
                {"type": "INTEGER", "name": "decimal_places", "value": "0"},
                {"type": "INTEGER", "name": "angle", "value": "270"}]}

def w_graph(gname, name, x, y, w=36, h=6):
    return {"type": "graph", "name": name, "x": str(x), "y": str(y),
            "width": str(w), "height": str(h),
            "fields": [
                {"type": "GRAPH", "name": "graphid.0",
                 "value": {"host": TPL, "name": gname}},
                # reference must be unique per dashboard (cross-widget
                # addressing namespace); deterministic + collision-free
                # via the object-seeded uuid.
                {"type": "STRING", "name": "reference",
                 "value": U("widget-" + name + "|" + gname)[:5].upper()}]}

# 8.0 canonical template-dashboard shape (verified against official
# "Ruckus UnLeashed by SNMP" export): dashboard keys are
# uuid/name/auto_start/pages and PAGES carry ONLY "widgets" - a page
# "name" makes the importer silently drop the whole dashboard.
dashboards = [{
    "uuid": U("dashboard-ngaf"),
    "name": "Sangfor NGAF",
    "auto_start": "NO",
    "pages": [
        {"widgets": [
            w_item("sangfor.device.name", "Device name", 0, 0, 18, 1),
            w_item("sangfor.software.version", "SangforOS", 18, 0, 18, 1),
            w_item("sangfor.af.version", "AF build", 36, 0, 36, 1),
            w_gauge("sangfor.cpu.util.1m", "CPU utilization", 0, 1, 8, 3),
            w_gauge("sangfor.mem.util", "Memory usage", 8, 1, 8, 3),
            w_item("sangfor.sessions.current", "Current sessions", 16, 1, 10, 3),
            w_item("sangfor.device.status", "Device status", 26, 1, 10, 3),
            w_item("sangfor.ha.status", "HA status", 36, 1, 10, 3),
            w_item("system.hw.uptime[hrSystemUptime.0]", "Uptime", 46, 1, 10, 3),
            w_graph("Sangfor NGAF: Throughput", "System throughput", 0, 4, 36, 6),
            w_graph("Sangfor NGAF: Sessions", "Sessions", 36, 4, 36, 6)]},
        {"widgets": [
            w_graph("Sangfor NGAF: CPU utilization", "CPU", 0, 0, 36, 6),
            w_graph("Sangfor NGAF: Memory", "Memory", 36, 0, 36, 6)]},
    ]}]

# ================= valuemaps =================
def valuemap(name, pairs):
    return {"uuid": U("vm-" + name), "name": name,
            "mappings": [{"value": v, "newvalue": t} for v, t in pairs]}

valuemaps = [
    valuemap("Sangfor: device status",
             [("0", "Warning"), ("1", "Normal")]),
    valuemap("Sangfor: HA enable",
             [("0", "disabled"), ("1", "enabled")]),
    valuemap("Sangfor: HA mode",
             [("0", "invalid"), ("1", "master-master"), ("2", "master-slave"),
              ("3", "mirror")]),
    valuemap("Sangfor: HA status",
             [("0", "invalid"), ("1", "init"), ("4", "master"), ("5", "slave")]),
    valuemap("Sangfor: HA sync state",
             [("0", "invalid"), ("1", "sync running"), ("2", "sync end"),
              ("3", "unknown")]),
    valuemap("Sangfor: hw state",
             [("0", "abnormal"), ("1", "normal")]),
    valuemap("Sangfor: if oper status",
             [("1", "up"), ("2", "down"), ("3", "testing"), ("4", "unknown"),
              ("5", "dormant"), ("6", "notPresent"), ("7", "lowerLayerDown")]),
    valuemap("Sangfor: if admin status",
             [("1", "up"), ("2", "down"), ("3", "testing")]),
]

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
       "tags": [{"tag": "class", "value": "network"},
                {"tag": "target", "value": "sangfor"},
                {"tag": "component", "value": "firewall"},
                {"tag": "vendor", "value": "Sangfor"}],
       "macros": macros,
       "valuemaps": valuemaps,
       "dashboards": dashboards}
# NOTE (8.0 JSON format): template-level graphs go under
# zabbix_export.graphs (sibling of templates), NOT inside the template
# object - verified against official template exports. graph_prototypes
# inside discovery rules DO stay nested.

doc = {"zabbix_export": {
    "version": "8.0",
    "template_groups": [{"uuid": U("group"), "name": TGROUP}],
    "templates": [tpl],
    "graphs": graphs}}

_here = Path(__file__).resolve().parent
out = (_here.parent if _here.name == "scripts" else _here) / "template_sangfor_ngaf_snmp.json"
with out.open("w", encoding="utf-8") as f:
    json.dump(doc, f, indent=2, ensure_ascii=False)
print("written", out)
print("items:", len(items), "lld:", len(drs))
