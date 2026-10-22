# Glossary

| Term | Meaning |
|------|---------|
| **Adapter** | Module that translates between the canonical model and one emulator's config. |
| **Binding** | `target ← source`: one console input driven by one physical input expression. |
| **Brand** | Controller manufacturer (Sony, 8BitDo). A controller scope level. |
| **Canonical model** | map-helper's emulator-independent representation of mappings. |
| **Claim** | A user's statement of what model a device really is ("this Xbox 360 ID is actually an 8BitDo Pro 2"). |
| **Content scope** | Where a rule applies: global, system, emulator, game. |
| **Controller scope** | Which controllers a rule applies to: device, model, family, brand, style, any. |
| **Device** | One physical controller unit, with a stable id (BT MAC / serial). |
| **Drift** | Managed keys changed by something other than map-helper since our last write. |
| **Family** | A product line across revisions and connection types (all DualShock 4s). |
| **Global-swap** | Adapter strategy: rewrite the emulator's global input config at each launch. |
| **Hook** | The line in an EmuDeck launcher (or upstream hook dir) that calls `mh-run`. |
| **Layout** | Description of a console's controller(s) and inputs (`data/layouts/*.json`). |
| **Managed keys** | The exact config keys/sections map-helper is allowed to modify. |
| **Meta-binding** | System-agnostic alias (`meta.confirm`) expanded per system layout. |
| **Model** | Exact hardware model, identified by one or more VID:PID. |
| **Native mode** | Steam Input off for a controller; the emulator sees the real device. |
| **Pack** | A shareable bundle of rules (`.mhpack.json`). |
| **Passthrough mode** | Steam Input on with a 1:1 gamepad template; the emulator sees a Steam Virtual Gamepad. |
| **Positional** | Inputs named by physical position (`face_south`), not by label. |
| **Preset** | A rule template offered in the UI (positional, label-match, southpaw...). |
| **Pristine snapshot** | Backup of a config file before map-helper first touched it. |
| **Resolver** | Computes effective bindings from all matching rules. |
| **Rule** | A partial set of bindings/options + `applies_to` (controller scope × content scope) + source. |
| **Slot** | Player number (P1..Pn) assigned to a device for a launch. |
| **Source (layer)** | Where a rule comes from: shipped, pack, user. |
| **Style** | Layout family whatever the brand: playstation, xbox, nintendo, sega6, arcade8, n64, steamdeck. |
| **Trace** | Per-binding explanation of which rule won and which were shadowed. |
