#!/usr/bin/env python3
"""Generate Zabbix 8.0 template XML from Sangfor MIB (enterprises 35047)."""
import uuid, datetime
from xml.etree import ElementTree as ET

BASE = ".1.3.6.1.4.1.35047"      # sangfor ::= enterprises 35047
GEN = BASE + ".1"                 # general ::= { sangfor 1 }
TPL = "Sangfor NGAF by SNMP"
GNAME = "Templates/Network devices"

def U():
    return uuid.uuid4().hex

root = ET.Element("zabbix_export")
ET.SubElement(root, "version").text = "8.0"
ET.SubElement(root, "date").text = datetime.datetime.now(
    datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

groups = ET.SubElement(root, "groups")
g = ET.SubElement(groups, "group")
ET.SubElement(g, "uuid").text = U()
ET.SubElement(g, "name").text = GNAME

templates = ET.SubElement(root, "templates")
t = ET.SubElement(templates, "template")
ET.SubElement(t, "uuid").text = U()
ET.SubElement(t, "template").text = TPL
ET.SubElement(t, "name").text = TPL
ET.SubElement(t, "description").text = (
    "Sangfor NGAF monitoring via private SANGFOR-MIB (enterprises 35047), "
    "converted from the vendor MIB file SANGFOR-MIB.txt. "
    "Requires SNMP v2c or later (Counter64 objects). "
    "Verified against a live NGAF running AF8.0.108.657: sfIfInRate/"
    "sfIfOutRate are instantaneous byte/s gauges (x8 only); sfIfInPkts/"
    "sfIfOutPkts and drops are cumulative counters (change per second); "
    "memory counters are kB, disk counters MB.")
tg = ET.SubElement(t, "groups")
g2 = ET.SubElement(tg, "group")
ET.SubElement(g2, "name").text = GNAME

X8 = [("MULTIPLIER", "8")]          # instantaneous byte/s -> bit/s gauge
CPS = [("CHANGE_PER_SECOND", None)]
K2B = [("MULTIPLIER", "1024")]
M2B = [("MULTIPLIER", "1048576")]

def render_item(parent, it):
    x = ET.SubElement(parent, "item")
    ET.SubElement(x, "uuid").text = it.get("uuid", U())
    ET.SubElement(x, "name").text = it["name"]
    ET.SubElement(x, "key").text = it["key"]
    if it.get("desc"):
        ET.SubElement(x, "description").text = it["desc"]
    if it.get("calc"):
        ET.SubElement(x, "type").text = "CALCULATED"
        ET.SubElement(x, "delay").text = "1m"
        ET.SubElement(x, "params").text = it["calc"]
    else:
        ET.SubElement(x, "type").text = "SNMP_AGENT"
        ET.SubElement(x, "snmp_oid").text = it["oid"]
        ET.SubElement(x, "snmp_community").text = "{$SANGFOR.SNMP.COMMUNITY}"
        ET.SubElement(x, "delay").text = "{$SANGFOR.UPDATE.FREQ}"
    ET.SubElement(x, "history").text = it.get("history", "7d")
    ET.SubElement(x, "value_type").text = it.get("vtype", "FLOAT")
    if it.get("units"):
        ET.SubElement(x, "units").text = it["units"]
    if it.get("pre"):
        pp = ET.SubElement(x, "preprocessing")
        for i, typ in enumerate(it["pre"], start=1):
            step = ET.SubElement(pp, "step")
            ET.SubElement(step, "type").text = typ[0]
            if typ[1] is not None:
                ET.SubElement(step, "parameter").text = typ[1]
            ET.SubElement(step, "statement").text = str(i)
    if it.get("tags"):
        tel = ET.SubElement(x, "tags")
        for tgname, tgval in it["tags"]:
            te = ET.SubElement(tel, "tag")
            ET.SubElement(te, "tag").text = tgname
            ET.SubElement(te, "value").text = tgval
    if it.get("trig"):
        trs = ET.SubElement(x, "triggers")
        tr = ET.SubElement(trs, "trigger")
        ET.SubElement(tr, "uuid").text = U()
        ET.SubElement(tr, "expression").text = it["trig"]["expr"]
        ET.SubElement(tr, "name").text = it["trig"]["name"]
        ET.SubElement(tr, "priority").text = it["trig"]["prio"]
    return x

def render_trigger_prototype(parent, tr):
    x = ET.SubElement(parent, "trigger")
    ET.SubElement(x, "uuid").text = U()
    ET.SubElement(x, "expression").text = tr["expr"]
    ET.SubElement(x, "name").text = tr["name"]
    ET.SubElement(x, "priority").text = tr["prio"]

def render_lld(parent, d):
    x = ET.SubElement(parent, "discovery_rule")
    ET.SubElement(x, "uuid").text = U()
    ET.SubElement(x, "name").text = d["name"]
    ET.SubElement(x, "key").text = d["key"]
    if d.get("desc"):
        ET.SubElement(x, "description").text = d["desc"]
    ET.SubElement(x, "type").text = "SNMP_AGENT"
    ET.SubElement(x, "snmp_oid").text = d["oid"]
    ET.SubElement(x, "snmp_community").text = "{$SANGFOR.SNMP.COMMUNITY}"
    ET.SubElement(x, "delay").text = "{$SANGFOR.DISCOVERY.FREQ}"
    ET.SubElement(x, "status").text = "ENABLED"
    f = ET.SubElement(x, "filter")
    ET.SubElement(f, "evaltype").text = "AND"
    if d.get("filter"):
        conds = ET.SubElement(f, "conditions")
        for macro, value, op in d["filter"]:
            c = ET.SubElement(conds, "condition")
            ET.SubElement(c, "macro").text = macro
            ET.SubElement(c, "value").text = value
            ET.SubElement(c, "operator").text = op
    ET.SubElement(x, "lifetime").text = "30d"
    ip = ET.SubElement(x, "item_prototypes")
    tp = None
    for it in d["protos"]:
        render_item(ip, it)
        if it.get("trig") and tp is None:
            tp = ET.SubElement(x, "trigger_prototypes")
        if it.get("trig"):
            render_trigger_prototype(tp, it["trig"])
    return x

def TR(prio, expr, name):
    return {"prio": prio, "expr": expr, "name": name}

# =============== scalar items ===============
items_el = ET.SubElement(t, "items")

def I(**kw):
    kw.setdefault("tags", [])
    render_item(items_el, kw)

I(name="Device description", key="sangfor.device.descr", vtype="CHAR",
  oid=GEN + ".1.0", desc="sfDeviceDescr")
I(name="Device name", key="sangfor.device.name", vtype="CHAR",
  oid=GEN + ".17.0", desc="sfSysDevName")
I(name="Software version", key="sangfor.software.version", vtype="CHAR",
  oid=GEN + ".18.0", desc="sfSysSoftVersion")
I(name="AF version", key="sangfor.af.version", vtype="CHAR",
  oid=GEN + ".24.0", desc="afSysSoftVersion")
I(name="Serial number", key="sangfor.serial.number", vtype="CHAR",
  oid=GEN + ".40.0", desc="sfSnGW (serial number of the appliance)")

I(name="Device status", key="sangfor.device.status",
  oid=GEN + ".12.0", desc="sfDeviceStatus: 0 - Warning, 1 - Normal",
  tags=[("component", "health")],
  trig=TR("WARNING", "last(/%s/sangfor.device.status)=0" % TPL,
          "Device reports WARNING status on {HOST.NAME}"))

I(name="CPU utilization (30s)", key="sangfor.cpu.util.30s", units="%",
  oid=GEN + ".19.4.0", desc="sfCpuAllCostRateLast30Sec",
  tags=[("component", "cpu")])
I(name="CPU utilization (1 min)", key="sangfor.cpu.util.1m", units="%",
  oid=GEN + ".19.5.0", desc="sfCpuAllCostRateLast1Min",
  tags=[("component", "cpu")],
  trig=TR("AVERAGE",
          "last(/%s/sangfor.cpu.util.1m)>{$SANGFOR.CPU.MAX}" % TPL,
          "High CPU utilization: over {$SANGFOR.CPU.MAX}% on {HOST.NAME}"))
I(name="CPU utilization (5 min)", key="sangfor.cpu.util.5m", units="%",
  oid=GEN + ".19.6.0", desc="sfCpuAllCostRateLast5Min",
  tags=[("component", "cpu")])
I(name="CPU core count", key="sangfor.cpu.num",
  oid=GEN + ".21.0", desc="sfCpuNum", tags=[("component", "cpu")])

I(name="Memory total", key="sangfor.mem.total", units="B",
  oid=GEN + ".13.4.0", desc="sfIntSysTotalMemory (kB -> B)",
  pre=K2B, tags=[("component", "memory")])
I(name="Memory free", key="sangfor.mem.free", units="B",
  oid=GEN + ".13.3.0", desc="sfIntSysFreeMemory (kB -> B)",
  pre=K2B, tags=[("component", "memory")])
I(name="Memory usage", key="sangfor.mem.util", units="%",
  oid=GEN + ".13.5.0", vtype="CHAR" if False else "FLOAT",
  desc="sfSysMemoryUsage - device-reported usage % (returns a numeric "
       "string; regex-extracted). Free/total would give a different "
       "number because the device counts cache/buffer as available.",
  pre=[("REGEX_EXTRACT", "([0-9]+)")],
  tags=[("component", "memory")],
  trig=TR("AVERAGE", "last(/%s/sangfor.mem.util)>{$SANGFOR.MEM.MAX}" % TPL,
          "High memory usage: over {$SANGFOR.MEM.MAX}% on {HOST.NAME}"))
I(name="Swap total", key="sangfor.swap.total",
  oid=GEN + ".38.1.0", desc="sfMemTotalSwap (units as reported by device)")
I(name="Swap available", key="sangfor.swap.avail",
  oid=GEN + ".38.2.0", desc="sfMemAvailSwap (units as reported by device)")

I(name="Current sessions", key="sangfor.sessions.current",
  oid=GEN + ".27.3.0", desc="sfCurSession", tags=[("component", "sessions")])
I(name="New sessions", key="sangfor.sessions.new",
  oid=GEN + ".27.1.0", desc="sfNewSessions", tags=[("component", "sessions")])
I(name="Total sessions", key="sangfor.sessions.total",
  oid=GEN + ".27.2.0", desc="sfTotalSessions", tags=[("component", "sessions")])
I(name="New sessions per second", key="sangfor.sessions.new.persec",
  oid=GEN + ".27.4.0", desc="sfNewSessionPerSec",
  tags=[("component", "sessions")])
I(name="Online users", key="sangfor.users",
  oid=GEN + ".23.0", desc="sfUsers", tags=[("component", "users")])

I(name="Inbound throughput", key="sangfor.throughput.in",
  oid=GEN + ".48.2.0", desc="sfSysInThroughput (units as reported by device)",
  tags=[("component", "throughput")])
I(name="Outbound throughput", key="sangfor.throughput.out",
  oid=GEN + ".48.1.0", desc="sfSysOutThroughput (units as reported by device)",
  tags=[("component", "throughput")])

I(name="HA enabled", key="sangfor.ha.enabled",
  oid=GEN + ".64.1.0", desc="sfHAEnable: 0 - disabled, 1 - enabled",
  tags=[("component", "ha")])
I(name="HA mode", key="sangfor.ha.mode",
  oid=GEN + ".64.2.0",
  desc="sfHAMode: 0 - invalid, 1 - master-master, 2 - master-slave, 3 - mirror",
  tags=[("component", "ha")])
I(name="HA current status", key="sangfor.ha.status",
  oid=GEN + ".64.3.0",
  desc="sfHACurStatus: 0 - invalid, 1 - init, 4 - master, 5 - slave",
  tags=[("component", "ha")])
I(name="HA control link status", key="sangfor.ha.ctrllink",
  oid=GEN + ".64.6.0",
  desc="sfHACtrlLinkStatus: 0 - invalid, 1 - normal, 2 - abnormal",
  tags=[("component", "ha")],
  trig=TR("HIGH", "last(/%s/sangfor.ha.ctrllink)=2" % TPL,
          "HA control link is ABNORMAL on {HOST.NAME}"))
I(name="HA data link status", key="sangfor.ha.datalink",
  oid=GEN + ".64.7.0",
  desc="sfHADataLinkStatus: 0 - invalid, 1 - normal, 2 - abnormal",
  tags=[("component", "ha")],
  trig=TR("HIGH", "last(/%s/sangfor.ha.datalink)=2" % TPL,
          "HA data link is ABNORMAL on {HOST.NAME}"))
I(name="HA sync state", key="sangfor.ha.sync",
  oid=GEN + ".64.8.0",
  desc="sfHASyncState: 0 - invalid, 1 - sync running, 2 - sync end, 3 - unknown",
  tags=[("component", "ha")])

# =============== LLD ===============
dr_el = ET.SubElement(t, "discovery_rules")

IF = GEN + ".34.1"   # sfIfTable
DK = GEN + ".5.1"    # sfDiskTable
CC = GEN + ".20.1"   # sfCpuCostRateTable
FN = GEN + ".14.1"   # sfSysFanTable
PW = GEN + ".15.1"   # sfSysPowerTable
TS = GEN + ".59.1"   # sfTempSensorTable

def P(name, key, oid, units="", pre=None, vtype="FLOAT", desc="", trig=None,
      tags=(), history="7d"):
    return dict(uuid=None, name=name, key=key, oid=oid, units=units,
                pre=pre, vtype=vtype, desc=desc, trig=trig, tags=list(tags),
                history=history)

render_lld(dr_el, dict(
    name="Interface discovery", key="sangfor.if.discovery", oid=IF + ".2",
    desc="Interfaces from SANGFOR-MIB::sfIfTable (column sfIfName).",
    filter=[("{#SNMPVALUE}", "^(?!(l.o|Loopback|lo$))", "MATCHES_REGEX")],
    protos=[
        P("Interface {#SNMPVALUE}: Inbound traffic", "sangfor.if.in.bps[{#SNMPINDEX}]",
          IF + ".8.{#SNMPINDEX}", "bps", X8, vtype="FLOAT",
          desc="sfIfInRate - instantaneous byte/s (verified on AF 8.0.108), x8 -> bit/s",
          tags=[("component", "network")]),
        P("Interface {#SNMPVALUE}: Outbound traffic", "sangfor.if.out.bps[{#SNMPINDEX}]",
          IF + ".9.{#SNMPINDEX}", "bps", X8, vtype="FLOAT",
          desc="sfIfOutRate - instantaneous byte/s (verified on AF 8.0.108), x8 -> bit/s",
          tags=[("component", "network")]),
        P("Interface {#SNMPVALUE}: Inbound packets rate", "sangfor.if.in.pps[{#SNMPINDEX}]",
          IF + ".13.{#SNMPINDEX}", "pps", CPS, vtype="UNSIGNED",
          desc="sfIfInPkts (Counter64 -> packets/s)",
          tags=[("component", "network")]),
        P("Interface {#SNMPVALUE}: Outbound packets rate", "sangfor.if.out.pps[{#SNMPINDEX}]",
          IF + ".14.{#SNMPINDEX}", "pps", CPS, vtype="UNSIGNED",
          desc="sfIfOutPkts (Counter64 -> packets/s)",
          tags=[("component", "network")]),
        P("Interface {#SNMPVALUE}: Inbound discards", "sangfor.if.in.drop[{#SNMPINDEX}]",
          IF + ".15.{#SNMPINDEX}", "ps", CPS, vtype="UNSIGNED",
          desc="sfIfInDrop (Counter64 -> rate)",
          tags=[("component", "network")],
          trig=TR("WARNING",
                  "last(/%s/sangfor.if.in.drop[{#SNMPINDEX}])>{$SANGFOR.IF_DROP.MAX}" % TPL,
                  "Interface {#SNMPVALUE}: high inbound discard rate (>{ITEM.LASTVALUE1} ps)")),
        P("Interface {#SNMPVALUE}: Outbound discards", "sangfor.if.out.drop[{#SNMPINDEX}]",
          IF + ".16.{#SNMPINDEX}", "ps", CPS, vtype="UNSIGNED",
          desc="sfIfOutDrop (Counter64 -> rate)",
          tags=[("component", "network")],
          trig=TR("WARNING",
                  "last(/%s/sangfor.if.out.drop[{#SNMPINDEX}])>{$SANGFOR.IF_DROP.MAX}" % TPL,
                  "Interface {#SNMPVALUE}: high outbound discard rate (>{ITEM.LASTVALUE1} ps)")),
        P("Interface {#SNMPVALUE}: IPv4 address", "sangfor.if.ipv4[{#SNMPINDEX}]",
          IF + ".4.{#SNMPINDEX}", vtype="CHAR", desc="sfIfAddr",
          tags=[("component", "network")]),
    ]))

def disk_usage_calc(it):
    it["calc"] = ("(last(/%s/sangfor.disk.used[{#SNMPINDEX}])"
                  "/last(/%s/sangfor.disk.size[{#SNMPINDEX}]))*100" % (TPL, TPL))

dp_size = P("Disk {#SNMPVALUE}: Total space", "sangfor.disk.size[{#SNMPINDEX}]",
            DK + ".7.{#SNMPINDEX}", "B", M2B,
            desc="sfIntDiskSize (MB -> B)", tags=[("component", "disk")])
dp_used = P("Disk {#SNMPVALUE}: Used space", "sangfor.disk.used[{#SNMPINDEX}]",
            DK + ".8.{#SNMPINDEX}", "B", M2B,
            desc="sfIntDiskUsed (MB -> B)", tags=[("component", "disk")])
dp_avail = P("Disk {#SNMPVALUE}: Available space", "sangfor.disk.avail[{#SNMPINDEX}]",
             DK + ".9.{#SNMPINDEX}", "B", M2B,
             desc="sfIntDiskAvail (MB -> B)", tags=[("component", "disk")])
dp_temp = P("Disk {#SNMPVALUE}: Temperature", "sangfor.disk.temp[{#SNMPINDEX}]",
            DK + ".10.{#SNMPINDEX}", "\u00b0C",
            desc="sfDiskTemp", tags=[("component", "disk")],
            trig=TR("WARNING",
                    "last(/%s/sangfor.disk.temp[{#SNMPINDEX}])>{$SANGFOR.DISK_TEMP.MAX}" % TPL,
                    "Disk {#SNMPVALUE}: high temperature ({ITEM.LASTVALUE1})"))
dp_pct = P("Disk {#SNMPVALUE}: Space usage", "sangfor.disk.pused[{#SNMPINDEX}]",
           None, "%", desc="Calculated used/total",
           tags=[("component", "disk")],
           trig=TR("WARNING",
                   "last(/%s/sangfor.disk.pused[{#SNMPINDEX}])>{$SANGFOR.DISK.MAX}" % TPL,
                   "Disk {#SNMPVALUE}: space usage over {$SANGFOR.DISK.MAX}%"))
dp_pct["calc"] = ("(last(/%s/sangfor.disk.used[{#SNMPINDEX}])"
                  "/last(/%s/sangfor.disk.size[{#SNMPINDEX}]))*100" % (TPL, TPL))

render_lld(dr_el, dict(
    name="Disk discovery", key="sangfor.disk.discovery", oid=DK + ".2",
    desc="Filesystems from SANGFOR-MIB::sfDiskTable (column sfFilesystemName).",
    protos=[dp_size, dp_used, dp_avail, dp_pct, dp_temp]))

render_lld(dr_el, dict(
    name="CPU core discovery", key="sangfor.cpu.discovery", oid=CC + ".4",
    desc="Per-core load from SANGFOR-MIB::sfCpuCostRateTable (column sfCpuAll).",
    protos=[
        P("CPU core {#SNMPINDEX}: User time", "sangfor.cpu.user[{#SNMPINDEX}]",
          CC + ".2.{#SNMPINDEX}", "%", desc="sfCpuUser per core",
          tags=[("component", "cpu")]),
        P("CPU core {#SNMPINDEX}: System time", "sangfor.cpu.sys[{#SNMPINDEX}]",
          CC + ".3.{#SNMPINDEX}", "%", desc="sfCpuSys per core",
          tags=[("component", "cpu")]),
        P("CPU core {#SNMPINDEX}: CPU utilization", "sangfor.cpu.util[{#SNMPINDEX}]",
          CC + ".4.{#SNMPINDEX}", "%", desc="sfCpuAll per core",
          tags=[("component", "cpu")],
          trig=TR("WARNING",
                  "last(/%s/sangfor.cpu.util[{#SNMPINDEX}])>{$SANGFOR.CPU_CORE.MAX}" % TPL,
                  "CPU core {#SNMPINDEX}: utilization over {$SANGFOR.CPU_CORE.MAX}%")),
    ]))

render_lld(dr_el, dict(
    name="Fan discovery", key="sangfor.fan.discovery", oid=FN + ".2",
    desc="Fans from SANGFOR-MIB::sfSysFanTable (column sfFanName).",
    protos=[
        P("Fan {#SNMPVALUE}: Speed", "sangfor.fan.speed[{#SNMPINDEX}]",
          FN + ".3.{#SNMPINDEX}", "rpm", desc="sfFanSpeed",
          tags=[("component", "hardware")]),
        P("Fan {#SNMPVALUE}: State", "sangfor.fan.state[{#SNMPINDEX}]",
          FN + ".4.{#SNMPINDEX}", desc="sfFanState: 0 - abnormal, 1 - normal",
          tags=[("component", "hardware")],
          trig=TR("AVERAGE",
                  "last(/%s/sangfor.fan.state[{#SNMPINDEX}])=0" % TPL,
                  "Fan {#SNMPVALUE} is ABNORMAL on {HOST.NAME}")),
    ]))

render_lld(dr_el, dict(
    name="Power supply discovery", key="sangfor.psu.discovery", oid=PW + ".2",
    desc="PSUs from SANGFOR-MIB::sfSysPowerTable (column sfPowerName).",
    protos=[
        P("PSU {#SNMPVALUE}: State", "sangfor.psu.state[{#SNMPINDEX}]",
          PW + ".3.{#SNMPINDEX}", desc="sfPowerState: 0 - abnormal, 1 - normal",
          tags=[("component", "hardware")],
          trig=TR("HIGH",
                  "last(/%s/sangfor.psu.state[{#SNMPINDEX}])=0" % TPL,
                  "Power supply {#SNMPVALUE} is ABNORMAL on {HOST.NAME}")),
    ]))

render_lld(dr_el, dict(
    name="Temperature sensor discovery", key="sangfor.temp.discovery", oid=TS + ".2",
    desc="Temperature sensors from SANGFOR-MIB::sfTempSensorTable (column sfTempSensorName).",
    protos=[
        P("Sensor {#SNMPVALUE}: Temperature", "sangfor.temp.value[{#SNMPINDEX}]",
          TS + ".3.{#SNMPINDEX}", "\u00b0C", desc="sfTempSensorReading",
          tags=[("component", "hardware")]),
    ]))

# =============== macros ===============
macros_el = ET.SubElement(t, "macros")
for m, v, d in [
    ("{$SANGFOR.SNMP.COMMUNITY}", "public",
     "SNMP community used by all Sangfor items. Override on host level."),
    ("{$SANGFOR.UPDATE.FREQ}", "1m", "Update interval for metrics."),
    ("{$SANGFOR.DISCOVERY.FREQ}", "1h", "Low-level discovery interval."),
    ("{$SANGFOR.CPU.MAX}", "90", "CPU utilization (%) warning threshold."),
    ("{$SANGFOR.CPU_CORE.MAX}", "95", "Per-core CPU utilization (%) threshold."),
    ("{$SANGFOR.MEM.MAX}", "90", "Memory usage (%) warning threshold."),
    ("{$SANGFOR.DISK.MAX}", "85", "Filesystem usage (%) warning threshold."),
    ("{$SANGFOR.DISK_TEMP.MAX}", "70", "Disk temperature warning threshold."),
    ("{$SANGFOR.IF_DROP.MAX}", "1000",
     "Interface discard rate (ps) warning threshold. Lower it if your policy drops are noisy."),
]:
    mx = ET.SubElement(macros_el, "macro")
    ET.SubElement(mx, "macro").text = m
    ET.SubElement(mx, "value").text = v
    ET.SubElement(mx, "description").text = d

ET.indent(root, space="    ")
tree = ET.ElementTree(root)
out = "/home/eddie/.openclaw/agents/homelab/sangfor/template_sangfor_ngaf_snmp.xml"
with open(out, "wb") as fh:
    tree.write(fh, encoding="UTF-8", xml_declaration=True)
print("written", out)
# re-parse sanity check
ET.parse(out)
print("XML well-formed OK")
