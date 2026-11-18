# Backlog

Accepted improvements and roadmap ideas from external reviews (2026-11-17),
triaged against the actual v0.5.0 template. Items here are NOT yet
implemented; anything shipped moves to CHANGELOG.md.

## P0 — polish — DONE in v0.5.1 (2026-11-17)

- [x] **Template-level tags** (`class: network`, `target: sangfor`,
  `component: firewall`, `vendor: Sangfor`). Item-level `component:*` tags
  already exist (54/61 items); template-level tags are the official-guideline
  gap. Generator: add `tags` to the template object.
- [x] **Explicit `trends`** on numeric items (currently 0/61 set; Zabbix
  defaults apply). Suggested: `365d` for gauges/utilization, `90d` for
  high-cardinality rates (per-interface bps/pps). Generator default + override.
- [x] **Hysteresis on threshold triggers** (CPU/memory/disk): add recovery
  expressions below the warn threshold (e.g. CPU warn >90, recover <80) to
  stop flapping. Applies to scalar + prototype thresholds.
- [x] **Explicit LLD `lifetime` / `enabled_lifetime`**: currently unset
  (8.0 defaults apply — lost resources are cleaned after the default
  lifetime, so "orphans linger forever" is not true, but explicit values
  document intent). VERIFIED 8.0 semantics: lifetime default 7d (delete),
  enabled_lifetime default 0 + enabled_lifetime_type 2 (disable
  immediately); shipped lifetime 30d / enabled_lifetime 0.

## From review #3 (2026-11-17, score 9.2/10 — mostly accurate)

Accepted:
- [x] Document sfIfTable↔IF-MIB index alignment as a firmware-verified
  assumption with a re-verification procedure (done in
  docs/compatibility.md; valid catch — alignment was verified live but
  only stated in item descriptions).
- [ ] HA split-brain composite trigger idea: `sangfor.ha.status` = slave
  AND `sangfor.ha.ctrllink` = abnormal (failed failover indicator).
  Needs semantics review against a real HA pair before shipping; single
  verified device runs standalone (HA disabled), so cannot test live.

Rejected (with evidence):
- **Patch 1 "JSNUM return null + DISCARD_UNCHANGED_HEARTBEAT"**: technically
  wrong — returning null from JS preprocessing does not produce a graceful
  skip (numeric conversion still fails), and DISCARD_UNCHANGED_HEARTBEAT is
  a value-deduplication step, NOT an error handler. If stale-value
  tolerance is ever wanted, the correct mechanism is the step's
  `error_handler: DISCARD_VALUE`; current explicit-throw behaviour is
  deliberate (visible unsupported beats silently stale usage data).
- **Patch 3 "recovery OR icmpping=1"**: would reintroduce false recovery —
  a dead SNMP agent stops trap delivery while the device still pings, so
  trap silence + ICMP up is NOT evidence the attack ended. The existing
  AND `zabbix[host,snmp,available]=1` design is deliberate; a permanently
  broken SNMP agent is surfaced by the "No SNMP data collection" trigger.
- **"Built-in dashboards provide immediate value upon import"**: false on
  8.0.0 — nested dashboards are silently dropped by configuration.import
  (documented; install_dashboard.py is the working path).
- **"~60% SNMP load reduction" from dependent items**: invented figure;
  host already uses bulk=1 GETBULK aggregation and measured load is
  negligible (see walk[] entry below).
- Note: review #3's quoted trap keys ("snmpTrapOID.0s=") lost backslashes
  in its web-extractor ingestion; the shipped keys correctly use
  `\.0\s=\s` and are live-verified.

## From review #4 (DeepSeek share link, 2026-11-18, score 8.0/10)

Accepted — DONE in v0.5.2 (2026-11-18):
- [x] **DISCARD_UNCHANGED_HEARTBEAT (1h) on discrete-state poll items**:
  device.status, ha.enabled/mode/status/ctrllink/datalink/sync, plus
  per-interface operstatus/adminstatus and fan/psu state prototypes.
  Cuts DB writes for values that rarely change; last()-based triggers
  unaffected. MUST NOT be applied to trap items (would break nodata()
  recovery), to uptime items (change()-based restart trigger), or to
  system.name (rename trigger compares consecutive values).

Accepted as an ops note — DONE on the live server (2026-11-18, host
wflx06): liveness trigger "Zabbix SNMP trapper process is not running"
(nodata 5m, HIGH) on the official health template's existing
zabbix[process,snmp trapper,avg,busy] item. Not part of this template
(server-side concern). Original note:
- [x] Trapper-health monitoring: if snmptrapd/the Zabbix snmp trapper
  dies while SNMP polling stays up, trap silence after
  {$SANGFOR.TRAP_PROBLEM_HOURS} looks like recovery. The recovery gate
  checks SNMP availability, not trapper liveness. Mitigation belongs on
  the Zabbix server/proxy health monitoring (internal item
  zabbix[process,snmp trapper,avg,busy] / process check), not on the
  firewall template.

Rejected / stale (with evidence):
- **"Missing mandatory class/target tags"** — STALE: added in v0.5.1
  (class: network, target: sangfor, component: firewall, vendor: Sangfor;
  verified in shipped JSON). The review read the file partially.
- **"Add hysteresis to all threshold triggers"** — STALE: v0.5.1 already
  ships hysteresis on all five threshold triggers (CPU scalar + per-core,
  memory, disk space, disk temperature).
- **Patch 3 walk[] master with JSONPATH "$"** — technically wrong as
  written: raw SNMP walk output is not JSON; it needs the SNMP walk to
  JSON preprocessing step first. The architecture direction itself is
  already tracked below (walk[] master + dependent items, deferred with
  measured justification: bulk=1 GETBULK already enabled, load negligible).
- **"Make all metric triggers depend on No-SNMP trigger"** — not official
  practice; unsupported items stop producing values so last()-based
  metric triggers cannot fire new problems during an SNMP outage. The
  official dependency chain (already ported) covers ICMP/loss/response.
- **"CPU 30s history 7d is heavy, use 1d"** — 7d matches official
  templates; storage cost trivial at 1/min cadence. No change.
- **"Value map for trap severity"** — redundant: trap items are LOG text;
  severity is already expressed per-trap via trigger priority.
- **"Ensure dashboard auto-imports with template"** — impossible on
  8.0.0 (nested dashboards silently dropped by configuration.import);
  install_dashboard.py is the documented working path.

## From review #6 (main v0.5.3→v0.5.5 diff review, 2026-11-18)

Accurate reviewer; all claims verified against code, point 2 settled by
live scratch tests.

Accepted — DONE in v0.5.6 (2026-11-18):
- [x] **BUG (most severe): configure_link_alerts.py deletes alert macros
  for ports that are down or have no value at run time** (line ~145
  `elif not want_on and cur is not None`). A critical WAN port down during
  a helper run loses its manually-enabled macro -> fault alerting silently
  disabled. Also fires when the device is unreachable (empty lastvalue).
  Fix: NEVER remove macros because of down/unknown state; skip ports with
  no status value; restrict removal to virtual interfaces and vanished
  interfaces, behind an explicit --prune flag. Docs must state this.
- [x] **Scope misclassification**: "High ICMP ping loss/response time"
  fall to availability (should be performance); fan/PSU ABNORMAL fall to
  availability (should be fault - checker allows fault, nothing uses it).
  Descriptions are one generic sentence per scope. Fix: explicit
  scope+description per trigger at definition site, drop name-substring
  guessing (_scope_for/_decorate).
- [x] **Virtual-interface regex drift**: template override uses
  `^(vpntun|ssltun|veth|tun|tap|lo)` (matches ANY lo* name), helper uses
  `...|lo$`. Two copies drift. Fix: single macro
  {$SANGFOR.IF.VIRTUAL.MATCHES} referenced by the LLD override; helper
  reads the template macro (or shares one constant).
- [x] Version string duplicated (generator + CHANGELOG): single VERSION
  constant in generator.
- [x] api() duplicated in install_dashboard.py + configure_link_alerts.py:
  shared module.
- [x] Docs: first deployment on hosts with macro default 0 produces a
  burst of coverage INFO notices (expected; mention in README).

Point 2 settled by LIVE scratch tests (both cleaned up):
- Reviewer's literal form `{$MACRO:regex:"..."}` AT THE USAGE SITE
  (inside the trigger expression): DOES NOT WORK on 8.0 (scratch trigger
  never fired).
- Documented form - regex in the macro DEFINITION
  ({$ZZ.CTX:regex:"^cpu"}=2), concrete context at usage
  ({$ZZ.CTX:"cpu.num"}): WORKS (scratch problem fired).
- CONSEQUENCE: the template ALREADY uses {$SANGFOR.IF.LINK.ALERT:"{#SNMPVALUE}"}
  at usage, so a host macro {$SANGFOR.IF.LINK.ALERT:regex:"^(eth9|eth10)$"}=1
  already covers multiple ports with NO template change. Optional helper
  enhancement: emit grouped regex macros; per-port macros stay the
  default (explicit/auditable). Document the regex-definition option.

Priority bump (reviewer argument accepted - the v0.5.4 incident proved
static checks cannot catch import-time failures):
- [x] **TOP PRIORITY: live-import CI job** — DONE in v0.5.6 - spin Zabbix 8.0 server+web+db
  containers in CI, configuration.import (two-pass tolerated), then assert
  via trigger.get/triggerprototype.get that live counts == JSON counts
  (export under-reports prototypes - use the get APIs). Also validates
  vendor block acceptance ("Community (eddieau)" already imports fine on
  the live server, but CI should pin it).

## Coverage-drift solution (Eddie question 2026-11-18, shipped v0.5.5)

- [x] New-port-added-later blind spot: INFO coverage-notice trigger
  prototype (oper=1 AND admin=1 AND link-alert macro=0) + LLD override
  excluding virtual interfaces. Auto-detects, operator decides (no
  auto-config mutation). Optional companion: scheduled re-run of
  configure_link_alerts.py (option B) - not requested, not implemented.

## v0.5.4 incident note (2026-11-18)

While applying review #5 live, discovered that re-imports had been
silently skipping ALL trigger changes since v0.5.1 (hysteresis/tags/
firmware trigger never applied). Root cause: full anchored strings as
find() regexp pattern literals are rejected by this server's import
parser, and one bad expression skips the whole trigger batch while the
API returns true. Fixed in v0.5.4 (bare-name patterns; anchored keys
unchanged) + checker rule. Live fully restored and verified: 94/94 host
triggers tagged, 0 unsupported, attack alerting re-fired. Also learned:
configuration.export under-reports trigger prototypes (use
triggerprototype.get); partial imports can lose template macros.

## From review #5 (local HEAD f1042f6, 2026-11-18, score ~8.7/10)

The most rigorous review so far: read generator/checker/CI/installer in
full, measured the JSON, and explicitly excluded already-fixed findings.
All factual claims verified true against HEAD.

Accepted — DONE in v0.5.3 (2026-11-18):
- [x] **Trigger scope tags + descriptions** (0/33 tagged, 1/33 described):
  add scope/desc args to TR/TRH; scopes availability/performance/capacity/
  security/notice. Enables SOC routing on security events.
- [x] **Interface LLD operator filter macros** {$SANGFOR.IF.NAME.MATCHES}
  (default .*) / {$SANGFOR.IF.NAME.NOT_MATCHES} (default ^$ = exclude
  nothing) — non-breaking, lets operators drop tunnels/unused ports.
- [x] **Firmware-change trigger** on sangfor.software.version
  (change()<>0, INFO, manual_close) — official pattern.
- [x] **Vendor block** {"name":"Sangfor","version":"0.5.x"} — official
  templates carry it (verified present in official APC export); traceable
  upgrades from the UI.
- [x] **Uptime poll macro** {$SANGFOR.UPTIME.FREQ} default 1m (currently
  hardcoded 30s = ~2880 polls/day/item for a 1m-resolution signal).
- [x] **Link-down debounce**: min(oper,#2)=2 instead of last()=2 so one
  dropped poll / brief flap doesn't raise HIGH (opt-in macro unchanged).
- [x] **Checker additions**: require trigger tags+descriptions; assert
  hysteresis recovery strictly below threshold; README item-count vs JSON;
  enforce DISCARD_UNCHANGED_HEARTBEAT absent from trap/uptime/system.name.
- [x] **.gitattributes** `* text=auto eol=lf` + generator newline="\n"
  (Windows contributors would otherwise CRLF-break the CI diff).
- [x] install_dashboard.py: close the JSON file handle (with-open); detect
  expired/invalid token distinctly; check host is linked to the template.

Resolved by live read-only check (no code change needed):
- [x] **Session counter types** (finding 6): two samples 15 s apart prove
  sfNewSessions is a window gauge (695→676, decreases) and sfTotalSessions
  is static/round (1,080,000 unchanged while ~150 sessions created) — NOT
  cumulative per-second counters. CHANGE_PER_SECOND would be wrong; raw
  storage is correct. Documented in docs/compatibility.md.

Deferred / medium term:
- [ ] **HA failover event trigger** change(sangfor.ha.status)<>0 (INFO/
  WARNING, manual_close). Correct under dedup (changes always stored) but
  UNTESTABLE on the standalone device (HA disabled) — ship only with a
  real HA pair or clearly mark untested. Pairs with the split-brain idea.
- [ ] **Live-import CI job** (Zabbix 8.0 server+web+db containers, call
  configuration.import, tolerate the two-pass quirk). Catches import-time
  failures the static checker can't (dashboard drop, bare-name deps, LINE
  constant). ~15-20 min setup; worth it but heavier — schedule separately.
- [ ] Session-capacity trigger with macro threshold (needs confirmed
  sfTotalSessions semantics first).
- [ ] Second-device verification row in compatibility.md (settles most
  unverified caveats at once).

Cosmetic / no action now:
- {$SANGFOR.TRAP_PROBLEM_HOURS} holds "4h" (name misleads). Renaming breaks
  existing hosts — document only; alias in a breaking v0.6 if ever.
- Dashboard first row leaves cols 56-72 empty; nested dashboard still
  can't import on 8.0.0 (documented). Optional.

Already-rejected items the reviewer correctly did NOT re-raise: blanket
on-fail discard, blanket SNMP dependencies, recovery-on-ICMP-up.

## P1 — considered (needs design/verification first)

- [ ] **walk[] master + dependent items** for sfIfTable / disk / CPU-core
  tables (Zabbix 8.0 SNMP walk preprocessing). **DECISION (Eddie,
  2026-11-18): DO NOT implement now — held as a v0.6 candidate.**
  Gate: only start when polling latency or timeout problems are actually
  MEASURED (item update lag, SNMP poller busy %, device timeouts), not on
  guideline pressure. Current justification for holding: host interfaces
  already use `bulk=1` (combined GETBULK), measured load negligible on all
  three verified devices (0 unsupported, fresh data).
  **Hard constraint when implemented: item keys AND UUIDs MUST stay
  unchanged** so upgrades do not break history continuity (history/trends
  are keyed by itemid; a new key/UUID = new item = history reset). Design
  the master as an ADDITIONAL item and convert existing items to
  DEPENDENT in place (same key, same UUID, master_itemid added, snmp_oid
  removed); verify with the CI upgrade-path pass plus a live history
  continuity check (pre/post values on the same itemid).
- [ ] **HA group-table LLD** (`sfHAGroupTable`, general.64.9): MIB defines
  it, but first do a read-only walk on the reference device to confirm the
  firmware implements it (fan/PSU/temp tables turned out empty the same
  way). Add only if real data exists.
- [ ] **Macro/filter to disable hardware LLD rules** (fan/PSU/temp) on
  models that don't expose them. Empty-table behaviour is already
  documented (README + docs/compatibility.md) and silent; this is optional
  operator convenience.
- [ ] **Swap units**: still "as reported by device" — verify against the
  vendor UI / memory values on a live device, then set units + multiplier.

## P2 — roadmap ideas (nice-to-have, no commitment)

- [ ] Grafana dashboard JSON (official Zabbix datasource plugin) + short
  integration note. Native Zabbix dashboard already ships with the template.
- [ ] Webhook/media-type examples formatting Sangfor trap events (attack,
  HA, bypass) for chat platforms.
- [ ] "Health score" calculated item (weighted CPU + memory + session
  pressure + HA state + recent critical traps).
- [ ] Dashboard page "Security events" surfacing attack/rulebase/config
  trap items.
- [ ] HA-pair awareness: suppress/informational certain triggers on the
  standby unit (needs a reliable standby indicator; `sfHACurStatus` exists).
- [ ] VPN tunnel object discovery beyond interface-level (MIB exposes no
  per-tunnel session table on AF8.0; only `sfIpsecStatusTrap` — revisit on
  newer firmware).

## Rejected / already done (do not re-litigate)

- **Trap pairing not per-interface** — FIXED in v0.5.0: fail/normal trap
  pairs are event-log items (no triggers); authoritative per-interface
  link alerting polls IF-MIB ifOperStatus/ifAdminStatus (opt-in context
  macro). Review #2 still listed this as a gap; that claim is stale.
- **Legacy XML schema / deprecated `{host:key.last()}` syntax / missing
  LLD / missing tags / missing MIB docs / missing snmptrapd integration /
  enterprise OID 22274** (review #1) — all factually wrong for this repo:
  JSON 8.0 export, 33/33 modern trigger expressions, 6 LLD rules,
  component tags, full MIB table + troubleshooting docs, live-verified
  trap chain, enterprise OID 35047. Review #1's sample XML would not
  import (invalid `recovery_mode` constant, missing uuids, JSONPath on
  raw walk output).
- **Custom on-fail = discard for all preprocessing** (review #1) —
  rejected: items going unsupported on SNMP failure is correct, visible
  behaviour covered by the "No SNMP data collection" trigger; discarding
  values would silently mask outages. JSNUM already throws explicitly on
  non-numeric input.
- **fan/PSU/temp empty-result documentation** (review #2) — already
  documented in README and docs/compatibility.md.
