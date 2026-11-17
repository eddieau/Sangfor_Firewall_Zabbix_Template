# Contributing

Thanks for helping improve Sangfor NGAF monitoring in Zabbix.

## Before you open an issue

1. Check the [template README](README.md) — most quirks (instantaneous
   `sfIf*Rate` gauges, `sfSysDiskUsage`/`sfSnGW` missing on AF 8.0, the
   110.x vs 200.200.x trap families) are already documented there.
2. Confirm the NGAF firmware version you run (System > About, or
   `snmpget ... .1.3.6.1.4.1.35047.1.18.0`). Sangfor's private MIB coverage
   varies per model/firmware.
3. For traps: verify your snmptrapd resolves names — the trap line must
   contain `SANGFOR-MIB::sf...`/`SANGFOR-AF-MIB::sf...`, not numeric OIDs
   (see `docs/troubleshooting.md`).

## Pull requests

- **Do not hand-edit `template_sangfor_ngaf_snmp.json`.** Edit
  `scripts/gen_template.py` and regenerate:

  ```bash
  python3 scripts/gen_template.py
  ```

  The script writes the JSON to the repository root. Object UUIDs are
  content-seeded (`U("<kind>-<key>")`) — keep seeds unique and stable so
  re-imports update objects in place.
- One logical change per PR (a new item ≠ a threshold retune ≠ a README fix).
- Update `CHANGELOG.md` under an "Unreleased" heading.
- If you add a trap item, cross-check the notification name against the
  vendor MIB (`SANGFOR-MIB-COMPATIBLE.txt` for 110.x, `SANGFOR-MIB-AF.txt`
  for 200.200.x) and say in the PR which firmware you validated against.

## Zabbix 8.0 import gotchas (known, do not "fix" blindly)

- Trigger dependencies in the import JSON use the **bare** trigger name (no
  template prefix); on an empty database the first import can abort and must
  be repeated — a second identical import resolves. (A minimal repro for
  upstream is worth filing; do not treat the two-pass import as intended.)
- **Object identities are content-seeded UUIDs**: items are seeded by key,
  triggers by *name*. Renaming a trigger creates a NEW trigger on
  re-import, and the old one only disappears when importing with
  `triggers.deleteMissing: true`. Prefer additive changes; if you rename,
  call it out in the PR and CHANGELOG so users re-import with
  deleteMissing.
- `value_type` has no `BOOLEAN` — use `UNSIGNED`.
- Items have no community/security-name field; SNMP credentials are
  host-interface only (`hostinterface.create` no longer exists; embed
  `interfaces` in `host.create`/`host.update`).
- `REGEX` preprocessing with a second "output" parameter misbehaves on some
  builds; numeric extraction from strings uses `JAVASCRIPT`.

## Privacy

Never commit real device IPs, SNMP credentials/communities, trap passphrases
or full config dumps. Use RFC5737 documentation addresses in examples.
