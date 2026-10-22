# 01 — Vision & Scope

## Problem

People who emulate on a Steam Deck commonly:

- own several controllers (the Deck itself, DS4/DualSense, Xbox, Switch Pro, 8BitDo, arcade sticks),
- use 10+ emulators across 20+ systems,
- want controls that differ by controller ("on my DualSense I want gyro in Cemu",
  "on any 8BitDo use the Nintendo positional layout"),
- and lose their tweaks whenever an emulator updates, EmuDeck resets configs, or
  a controller turns up at a different SDL index.

What exists today:

| Tool | What it does | Gap |
|------|--------------|-----|
| Steam Input | Per game, per *controller type* remap to a virtual pad | Knows nothing about emulated console buttons; doesn't help with native gyro/touchpad passthrough |
| EmuDeck | Ships sane default configs for every emulator | Assumes one virtual Xbox-style pad; resets overwrite user changes |
| Steam ROM Manager | Applies Steam Input templates per parser | Steam Input layer only |
| RetroArch autoconfig / remaps | Per-device autoconfig, per-core/game remaps | RetroArch only |
| Per-emulator profiles (Dolphin, PCSX2, RPCS3...) | Profiles inside each emulator | 15 separate UIs, no shared controller identity, no auto-select |

**Nothing gives you one place to say "this controller (or every controller like
it), this system, these buttons" and have it applied everywhere, automatically.**

## Vision

> Plug in any controller. map-helper recognises it, and every emulator launches
> with the mapping you chose for *that controller*, *that kind of controller*,
> or *any controller* on *that system*. No menus, no surprises.

## Goals

1. **One canonical model** of mapping *rules*, scoped along two axes:
   - **controller scope**: exact device → model → family → brand → layout style → any
   - **content scope**: global → system → emulator → game
2. **Layered defaults.** Shipped defaults, optional community packs, and user rules stack, and the most specific rule wins *per binding*.
3. **Guided mapping UX** usable entirely in Game Mode with a controller: press-to-bind, presets, a test screen, and a clear "apply to…" scope picker.
4. **Automatic apply at launch**, based on the controllers actually connected.
5. **Durable.** Survives emulator updates, EmuDeck updates and resets, and controller reconnection order.
6. **Safe.** Never leaves an emulator config broken. Changes are always backed up and reversible, and uninstall restores the original state.
7. **Explainable.** For any binding, `map-helper explain` shows which rule it came from and why.
8. **Import.** Read existing emulator configs back into the model, so changes made in an emulator's own UI aren't lost.
9. **EmuDeck first.** Designed so RetroDECK, plain installs, Bazzite and other handhelds can be added via path providers.

## Non-goals (v1)

- Replacing Steam Input. We coexist with it (see [05](05-steam-input-strategy.md)).
- Keyboard/mouse mapping for PC games.
- Light guns (Sinden, GUN4IR), wheels and other exotic peripherals (possible later as controller styles).
- Windows. EmuDeck for Windows exists, but its paths and launch model differ. Keep the core portable, and don't ship it in v1.
- Authoring per-game *Steam Input* layouts (SRM and Steam already do this).
- A cloud sync service. Export/import files only; Syncthing or Decky Cloud Save can carry them.

## Personas

| Persona | Needs |
|---------|-------|
| **Casual Deck owner** | Plugs in a DS4 when docked. Wants it to "just work", maybe with Nintendo A/B flipped. Never edits files. Shipped defaults matter most here. |
| **Enthusiast** | Many controllers, wants gyro in Cemu and the Switch emulators, custom hotkeys, per-game tweaks for a few titles. Uses family/brand rules plus game overrides. |
| **Couch multiplayer host** | 2–4 mixed controllers. Cares about player order, and the Deck's built-in controls should NOT be P1 when docked. |
| **Tinkerer / contributor** | Writes an adapter for a new emulator or a controller DB entry. Needs a clear contract and tests. |

## Success criteria

- A casual user can map a DS4 for GameCube in Dolphin in **under 2 minutes** from Game Mode.
- "Apply to all DualShock 4" set once covers DS4 v1, DS4 v2, and both USB and Bluetooth connections.
- Reconnecting controllers in a different order **does not** change which mapping applies.
- An EmuDeck "reset configurations" followed by a launch restores the user's mappings **with no action** from them.
- `map-helper uninstall` returns every touched config file byte-for-byte to its pre-install state, or to the latest emulator-written state if the user chooses.
- Adding a new emulator adapter takes a contributor **under a day** with the template and test harness.

## Guiding principles

1. **Launch time is the source of truth.** We don't rely on background daemons racing emulators.
2. **We own a layer, not the world.** We only touch the input and hotkey sections of emulator configs.
3. **Positional by default, semantic by choice.** Physical button *positions* are the base vocabulary. "Label match" (Nintendo A = the button printed A) is a preset on top.
4. **Most specific wins, per binding.** Rules merge; they don't replace each other wholesale.
5. **Every fact about an emulator lives in its adapter**, with fixtures from real versions.
6. **Boring formats.** JSON on disk, with a published JSON Schema. Human-readable and diffable.
