#!/usr/bin/env python3
"""Generate Zabbix 8.0 template (JSON import format) from Sangfor MIB (enterprises 35047).

Format verified against configuration.export output of an official 8.0 template.
"""
import uuid, json, itertools

BASE = "1.3.6.1.4.1.35047"        # sangfor
GEN = BASE + ".1"                  # general ::= { sangfor 1 }
TPL = "Sangfor NGAF by SNMP"
TGROUP = "Templates/Network devices"

# Deterministic UUIDs (uuid5 from a stable counter) so re-importing a
# regenerated file updates objects in place instead of clashing on names.
# Caveat: keep generation order stable; inserting/removing items shifts the
# counter for later objects.
_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/eddieau/Sangfor_Firewall_Zabbix_Template")
_C = itertools.count(1)

def U():
    return uuid.uuid5(_NS, "sangfor-ngaf-%d" % next(_C)).hex

items = []
drs = []
macros = []

def snmp_item(name, key, oid, vtype="FLOAT", units="", desc="", pre=None,
              trig=None, tags=(), history="7d"):
    it = {"uuid": U(), "name": name, "type": "SNMP_AGENT", "snmp_oid": oid,
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
    it = {"uuid": U(), "name": name, "type": "CALCULATED", "key": key,
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
    return {"uuid": U(), "expression": expr, "name": name, "priority": prio}

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
          "get[" + GEN + ".48.2.0]",
          desc="sfSysInThroughput - instantaneous; units not stated in MIB "
               "(verify against vendor UI).", tags=[("component", "throughput")])
snmp_item("Sangfor: Outbound throughput", "sangfor.throughput.out",
          "get[" + GEN + ".48.1.0]",
          desc="sfSysOutThroughput - instantaneous; units not stated in MIB "
               "(verify against vendor UI).", tags=[("component", "throughput")])

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
    it = {"uuid": U(), "name": name, "type": "SNMP_AGENT",
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
    it = {"uuid": U(), "name": name, "type": "CALCULATED", "key": key,
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
    dr = {"uuid": U(), "name": name, "type": "SNMP_AGENT",
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
           "ps", CPS, desc="sfIfInDrop (cumulative counter -> rate).",
           tags=[("component", "network")],
           trig=TR("WARNING",
                   "last(/%s/sangfor.if.in.drop[{#SNMPINDEX}])>{$SANGFOR.IF_DROP.MAX}" % TPL,
                   "Interface {#SNMPVALUE}: high inbound discard rate on {HOST.NAME}")),
     proto("Interface {#SNMPVALUE}: Outbound discards",
           "sangfor.if.out.drop[{#SNMPINDEX}]", IF + ".16.{#SNMPINDEX}",
           "ps", CPS, desc="sfIfOutDrop (cumulative counter -> rate).",
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
     "Interface discard rate (ps) warning threshold."),
]:
    macros.append({"macro": m, "value": v, "description": d})

# ================= assemble =================
tpl = {"uuid": U(), "template": TPL, "name": TPL,
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
    "template_groups": [{"uuid": U(), "name": TGROUP}],
    "templates": [tpl]}}

out = "/home/eddie/.openclaw/agents/homelab/sangfor/template_sangfor_ngaf_snmp.json"
with open(out, "w") as f:
    json.dump(doc, f, indent=2, ensure_ascii=False)
print("written", out)
print("items:", len(items), "lld:", len(drs))
