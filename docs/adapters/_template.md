# Adapter: <Emulator name>

> Copy this file to `docs/adapters/<id>.md`. Every factual claim needs either a
> fixture reference or a **[VERIFY]** tag.

## Summary

| Field | Value |
|-------|-------|
| Adapter id | `<id>` |
| Systems | |
| EmuDeck install type | Flatpak `<app-id>` / AppImage / other |
| Versions covered | |
| Priority | P0 / P1 / P2 / P3 |
| Strategy | global-swap (+ profile-select / native per-game?) |

## Paths

| What | Flatpak | AppImage / native | RetroDECK |
|------|---------|-------------------|-----------|
| Config root | | | |
| Input file(s) | | | |
| Profiles | | | |
| Per-game | | | |

## Format

- Dialect, quirks (escaping, quoting, ordering), and whether it's saved on exit.
- Example excerpt from a fixture.

## Device references

- How the emulator refers to a controller (index / name / GUID / handler).
- What it looks like with Steam Input on (passthrough) vs off (native).

## Input naming table

| Canonical | Emulator token (passthrough) | Emulator token (native DS4) | Notes |
|-----------|------------------------------|-----------------------------|-------|
| `face_south` | | | |
| ... | | | |

## Console target table

| Canonical target | Emulator key |
|------------------|--------------|
| `<sys>.<type>.<input>` | |

## Managed keys

Exact list of keys/sections we write. Nothing else may change.

## Game id

How to get the id this emulator uses, from a ROM path. Sources, in order.

## Hotkeys

Where hotkeys live and what EmuDeck sets.

## Options support

Rumble, deadzones, gyro/motion, controller type, multitap, etc.

## Known pitfalls

## Fixtures

List of `tests/fixtures/<id>/<version>/...` and what each represents.
