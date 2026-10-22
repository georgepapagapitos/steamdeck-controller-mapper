# Example rules

One example per scope level. Together they show how layering works.

| File | Controller scope | Content scope | What it does |
|------|------------------|---------------|--------------|
| `01-any.global.hotkeys.json` | any | global | Hotkeys for every controller and emulator |
| `02-style.nintendo.snes.label-match.json` | style: nintendo | system: snes | Nintendo-style pads use label-match on SNES |
| `03-brand.8bitdo.global.meta-swap.json` | brand: 8bitdo | global | Swap confirm/cancel everywhere for all 8BitDo pads (meta-bindings) |
| `04-family.ds4.gc.json` | family: DualShock 4 | system: gc | All DS4s: GameCube layout + rumble |
| `05-model.dualsense-edge.ps2.paddles.json` | model: DualSense Edge | system: ps2 | Back paddles → L3/R3 on PS2 |
| `06-device.blue-ds4.global.deadzone.json` | device (one pad) | global | A worn stick gets a bigger deadzone |
| `07-any.game.melee.json` | any | game: GALE01 | Melee-specific tweak for every controller |
| `08-family.ds4.dolphin.wii.json` | family: DualShock 4 | emulator: dolphin + system: wii | Wii Nunchuk setup in Dolphin only |

## Worked resolution

Player 1 = "Blue DS4" (device `mac:aa:bb:cc:dd:ee:ff`, model `sony.ds4.v2`,
family `sony.dualshock4`, brand `sony`, style `playstation`), launching
**Melee (GALE01) in Dolphin**.

Candidate rules: 01, 04, 06, 07 (02/03 don't match the controller; 05 is the
wrong system/model; 08 is the wrong system).

| Key | Winner | Why |
|-----|--------|-----|
| `gc.standard.a` | 04 | Only 04 sets it |
| `gc.standard.z` | **07** | 04 and 07 both set it; 07 is `game` content scope (content outranks controller) |
| `options.rumble` | 04 | Only 04 |
| `options.deadzones.ls` | 06 | Only 06 |
| `hotkey.*` | 01 | Only 01 |
| everything else | adapter baseline | Not written |

`map-helper explain --emulator dolphin --system gc --game GALE01 --player 1` would print this table.
