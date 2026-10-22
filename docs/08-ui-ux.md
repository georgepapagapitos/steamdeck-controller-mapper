# 08 — UI / UX

Primary surface: a **Decky Loader plugin** in Game Mode, used entirely with a
controller. Secondary: the CLI. A desktop GUI is a later option.

## Design principles

1. **Ask about scope after the user shows intent.** The user maps first and
   picks "apply to…" at save time. Nobody thinks in scope levels up front.
2. **Always show glyphs for the controller in your hand** (✕○□△ on a DS4, ABXY on Xbox) and the console's own glyphs on the target side.
3. **Explain everything.** Every binding cell can show "from: *All DualShock 4 → GameCube* (your rule)".
4. **Undo is always one press away.** Every save keeps the previous rule version.

## Information architecture

```
map-helper (QAM panel)
├── Status: connected controllers + active slot order + mode (Passthrough/Native)
├── Map a controller            → Wizard
├── Rules                       → Rule list (filter by controller scope / system / emulator)
├── Controllers                 → Device registry (rename, claim model, link identities, pin slot)
├── Matrix                      → Full-screen: controllers × systems coverage grid
├── Defaults & packs            → Shipped defaults, community packs (enable/disable)
└── Settings                    → Player order policy, docked behaviour, hook status, backups, uninstall
```

The QAM panel is narrow, so the Matrix, Wizard and Rule editor open as
**full-screen routes**. Confirmed: `@decky/api` exports
`routerHook.addRoute(path, Component, props)` and `removeRoute(path)`. Decky's
own store and settings pages are routes registered the same way. Register
`/map-helper/wizard`, `/map-helper/matrix` and `/map-helper/rule/:id` in
`definePlugin`, remove them in `onDismount`, and open them with
`Navigation.Navigate(path); Navigation.CloseSideMenus();` (the template's
pattern). See [14 §3](14-packaging-permissions.md#3-frontend-api).

## Flow 1: New controller detected

```
┌───────────────────────────────────────────┐
│ 🎮 New controller: "Wireless Controller"   │
│ Looks like: DualShock 4 (v2)              │
│                                           │
│  [ Looks right ]   [ It's something else ]│
│  [ Map it now ]    [ Later ]              │
└───────────────────────────────────────────┘
```

- Ambiguous devices (Xbox 360 ID, Switch Pro ID) prompt: "Is this a genuine
  Xbox 360 pad, or an 8BitDo/other in X-mode?", with a searchable model list.
- **A Decky toast can't hold these buttons.** `toaster.toast()` takes
  `title`, `body`, `logo`/`icon`, `duration`, `critical`, `playSound` and a
  single `onClick`, with no action buttons. So the toast says "New controller:
  DualShock 4 (v2). Tap to set up", and `onClick` opens a modal or route with
  the four choices above.
- Detection, v1: the frontend subscribes to
  `SteamClient.Input.RegisterForControllerListChanges`, which reports each
  controller's `strName`, `unVendorID`, `unProductID`, `strSerialNumber`,
  `nControllerIndex` and `bWireless` (`@decky/ui` typings). On a change, it
  asks the backend to re-probe sysfs and match the device. This is
  event-driven and cheap, and it runs while the Steam UI is up, regardless of
  whether the QAM is open. **[VERIFY]** that pads with Steam Input disabled
  still appear in this list. Fallback: backend polls sysfs every few seconds.
  A udev notifier stays a v2 idea.

## Flow 2: The mapping wizard

**Step 1: Pick the controller** (defaults to the last one pressed)

**Step 2: Pick the system** (grid of console icons; recently played first)

**Step 3: Start from**

```
  ( ) Current mapping (what you'd get today)    ← default
  ( ) Preset: Positional / Label-match / Southpaw / Fightpad-6 / ...
  ( ) Copy from: [ another controller's rules for this system ]
  ( ) Blank
```

**Step 4: Press-to-bind**

```
┌──────────────────────────────────────────────────────────────┐
│  GameCube  ·  mapping for: DualShock 4                        │
│                                                              │
│      [GC controller illustration, "A" highlighted]           │
│                                                              │
│      Press the button you want for   Ⓐ  A                    │
│      Currently: ✕ Cross                                      │
│                                                              │
│  Hold ◯ on the Deck: skip  ·  Hold □ on the Deck: unbind     │
│  Progress ▓▓▓▓░░░░░░░░ 4/14                                  │
└──────────────────────────────────────────────────────────────┘
```

- Sticks: "Move the stick you want for Main Stick" detects the axis pair. Then "Push it UP" confirms orientation and inversion.
- Triggers: detects analog vs digital, and offers "use as analog" where the target supports it.
- **Input capture vs UI navigation conflict:** button presses during capture
  must not also navigate the Steam UI. Approach:
  - Capture listens **only to the selected device** (evdev/hidraw), and the UI
    is driven by the *other* controller (usually the Deck's built-in pad).
  - If the device being mapped is also the only controller, use a capture
    route whose single `Focusable` takes focus and swallows navigation. The
    `@decky/ui` 4.16 API is `onButtonDown` / `onButtonUp` (there is no
    `onGamepadButtonDown`), plus `onOKButton`, `onCancelButton`,
    `onSecondaryButton`, `onOptionsButton`, `onMenuButton`,
    `onGamepadDirection`, and `Focusable`'s `onCancel`. The event detail is
    `{ button: GamepadButton, is_repeat?, source }`. `GamepadButton` covers
    OK, CANCEL, SECONDARY, OPTIONS, BUMPER_L/R, TRIGGER_L/R, DIR_*, SELECT,
    START, L/RSTICK_CLICK, pad touch/click, REAR_LEFT/RIGHT_UPPER/LOWER (L4,
    L5, R4, R5), STEAM_GUIDE and STEAM_QUICK_MENU.
  - Feasibility (from existing plugins, not yet from our own prototype):
    handling `onCancelButton` / `onCancel` on the focused element replaces the
    default back action. SteamGridDB's logo positioner, a full-screen modal,
    binds B, X, Y, Menu and the D-pad this way. Another community plugin
    calls `preventDefault()` + `stopPropagation()` in `onButtonDown` and
    describes "unconsumed Ⓑ goes back to Steam". So B, the shoulders and the
    triggers look capturable while we hold focus. **Steam and QAM buttons
    almost certainly are not** (Steam handles them globally). Neither can
    be bound in the wizard, and neither can be the skip/confirm gesture.
    **[VERIFY]** in S4: B on a route with a consuming handler, L1/R1 on a
    route (no Tabs), and what happens when focus is lost (e.g. a toast
    steals it).
  - **UI events can't tell controllers apart.** `GamepadEvent` carries no
    controller index, and the buttons are Steam's UI actions after Steam
    Input's UI mapping, not physical codes. The UI layer is therefore only
    for *suppressing navigation* and the hold-to-confirm gesture. The actual
    binding still comes from the backend's evdev reader on the selected
    device ([14 §7](14-packaging-permissions.md#7-device-permissions)).
  - Optional second source: `SteamClient.Input.RegisterForControllerStateChanges`
    gives per-controller raw state (`unControllerIndex`, button bitmask
    including L4/R4/L5/R5, sticks, triggers, gyro) in Steam's normalised
    layout. It's useful for capturing the Deck's built-in pad or a pad Steam
    owns, and it's already used by community plugins for global shortcuts.
    **[VERIFY]** whether it reports pads with Steam Input disabled.
  - Confirm by **holding** a button for 1.5 s, which is never a valid single-press bind.
  - Fallback: "list mode", where each target is a dropdown of physical inputs. It's slower, but it always works.

**Step 5: Test**

A live view of the console layout: pressing physical buttons lights the
console buttons they're mapped to. This uses the same capture stream run
through the resolver with the *unsaved* rule on top.

**Step 6: Apply to…** (scope picker)

```
Apply this GameCube mapping to:

  Controllers                          Where
  ( ) Only this controller             (•) All GameCube games (every emulator)
      "Blue DS4"                       ( ) Only in Dolphin
  (•) All DualShock 4                  ( ) Only this game: [ pick / current ]
  ( ) All Sony controllers
  ( ) All PlayStation-style controllers
  ( ) Every controller

  ⚠ This will override 2 bindings from "All PlayStation-style → GameCube" (your rule)
  ⓘ Shipped default for GameCube still provides 6 bindings you didn't change

                     [ Save ]   [ Back ]
```

- Only levels that make sense for this controller are shown. For an unclaimed
  Xbox-360-ID pad, "All 8BitDo" only appears once it's been claimed as 8BitDo.
- The **conflict preview** comes from a dry-run resolve.
- The rule only stores the bindings the user changed compared to the starting
  point, unless they choose "Save full mapping". Small rules layer cleanly.

## Flow 3: Matrix view

```
                 NES  SNES  N64  GC   Wii  PS1  PS2  PSP  Switch ...
Deck built-in    ·    ·     ·    ·    ·    ·    ·    ·    ·
Blue DS4         F    F     F    F*   ·    S    S    ·    F
8BitDo Pro 2     B    B     B    B    B    ·    ·    ·    B
Xbox Series      ·    ·     ·    G    ·    ·    ·    ·    ·

Legend: · shipped defaults only   D device rule   M model   F family   B brand
        S style   A any   G game override   * game override exists too
```

Select a cell to see the resolved bindings, each with where it came from, and actions: Edit / Override for game / Reset to defaults.

## Flow 4: Rule list and editor

- Filter chips: controller scope, content scope, source (mine/pack/shipped), enabled.
- Each rule: label, scope summary, binding count, enable toggle, "explain", duplicate, delete.
- The editor is a table of `target → source` with a press-to-bind button per row, plus options (rumble, deadzone, gyro).

## Flow 5: Drift detected (emulator UI changes)

```
Dolphin's GameCube controls were changed outside map-helper
(since Oct 20, 14:02):  A: ✕ → ○,  B: ○ → ✕

  [ Keep Dolphin's changes → save as rule ]  (scope picker)
  [ Revert to my map-helper mapping ]
  [ Stop managing Dolphin GC controls ]
```

This shows on the next plugin open after a launch where drift was detected. At
launch time the default action is configurable: `prefer-mine` (default) or `prefer-emulator`.

We can also tell the user as soon as the game closes:
`SteamClient.GameSessions.RegisterForAppLifetimeNotifications` fires with
`bRunning: false` when a game exits. The frontend then asks the backend for
a drift check and toasts "Dolphin's controls changed. Tap to review". The
typings note that `unAppID` is 0 for non-Steam shortcuts, so this can't tell
*which* shortcut exited. The backend correlates with
`$STATE/last-launch.json` written by `mh-run`. **[VERIFY]**
`RegisterForGameActionStart`'s `appId` for shortcuts.

## Flow 6: Settings

- Player order policy (+ docked auto-switch)
- Steam Input mode guidance per controller type (read-only status + how to change)
- Launch integration status: "Steam shortcuts wrapped ✅ 142/142 · ES-DE event script ✅ · EmuDeck AutoMap off ✅" / "Repair" ([ADR-001](adr/001-apply-at-launch.md))
- Managed emulators: on/off per emulator
- Backups: list, restore, export
- Export/import rules (single file `.mhpack.json`)
- Uninstall: restore pristine or current-EmuDeck configs, remove hooks

## CLI parity

Every UI action maps to a CLI command (see [glossary](glossary.md) for terms):

```
map-helper devices [--json]
map-helper devices claim <device-id> <model>
map-helper rules list|show|add|edit|rm|enable|disable
map-helper explain --emulator dolphin --system gc [--game GALE01] [--player 1]
map-helper apply   --emulator dolphin [--system gc] [--game ...] [--dry-run]
map-helper import  --emulator dolphin --scope family:sony.dualshock4/system:gc
map-helper capture <device-id>          # prints normalized events (debug)
map-helper hooks status|install|repair|remove
map-helper backup list|restore <id>
map-helper doctor                        # full diagnostics bundle
map-helper uninstall [--restore pristine|current]
```

## Accessibility & polish

- Big targets, readable at handheld distance, works with the D-pad only.
- Remap support for players with one-handed setups (chords, holds) is a real use case. Keep chords available beyond hotkeys (later).
- Sounds/haptics on successful bind (Deck rumble).
- Localisation-ready strings from day one.

## Sources

Read on 2026-10-22. Packaging and permission details are in
[14](14-packaging-permissions.md#sources).

- `@decky/api` 1.1.3, `SteamDeckHomebrew/loader-api` @ `d1b7f16`: [`src/index.ts`](https://github.com/SteamDeckHomebrew/loader-api/blob/d1b7f16070777a0ada939cbacd3606eeba0574f5/src/index.ts) (`routerHook`, `toaster`, `callable`, `definePlugin`), [`src/types.ts`](https://github.com/SteamDeckHomebrew/loader-api/blob/d1b7f16070777a0ada939cbacd3606eeba0574f5/src/types.ts) (`ToastData`)
- Decky Loader v3.3.0 @ `00cd202`: [`frontend/src/router-hook.tsx`](https://github.com/SteamDeckHomebrew/decky-loader/blob/00cd202872b85868071b041c8f1b34e734147195/frontend/src/router-hook.tsx) (`addRoute`, `removeRoute`), [`frontend/src/plugin-loader.tsx`](https://github.com/SteamDeckHomebrew/decky-loader/blob/00cd202872b85868071b041c8f1b34e734147195/frontend/src/plugin-loader.tsx) (`/decky/store`, `/decky/settings` routes)
- Plugin template @ `90d0780`: [`src/index.tsx`](https://github.com/SteamDeckHomebrew/decky-plugin-template/blob/90d0780e882a17f5714fc6de044c645f22608290/src/index.tsx) (route + `Navigation.Navigate` pattern, toasts)
- `@decky/ui` 4.16.0 @ `10b929d`: [`src/components/FooterLegend.ts`](https://github.com/SteamDeckHomebrew/decky-frontend-lib/blob/10b929d2e92af179569fa1bb8f456cc5f57f28d5/src/components/FooterLegend.ts) (`GamepadButton`, `onButtonDown`, `onCancelButton`, `GamepadEventDetail`), [`src/components/Focusable.ts`](https://github.com/SteamDeckHomebrew/decky-frontend-lib/blob/10b929d2e92af179569fa1bb8f456cc5f57f28d5/src/components/Focusable.ts), [`src/globals/steam-client/Input.ts`](https://github.com/SteamDeckHomebrew/decky-frontend-lib/blob/10b929d2e92af179569fa1bb8f456cc5f57f28d5/src/globals/steam-client/Input.ts) (`RegisterForControllerListChanges`, `RegisterForControllerStateChanges`, `ControllerInfo`), [`src/globals/steam-client/GameSessions.ts`](https://github.com/SteamDeckHomebrew/decky-frontend-lib/blob/10b929d2e92af179569fa1bb8f456cc5f57f28d5/src/globals/steam-client/GameSessions.ts) (`RegisterForAppLifetimeNotifications`, `unAppID` caveat)
- Input-consuming plugins: [SteamGridDB `src/modals/LogoPositionerModal.tsx`](https://github.com/SteamGridDB/decky-steamgriddb/blob/26682f6a58b5dad774abe740ee3f9bad38296496/src/modals/LogoPositionerModal.tsx) (Focusable with `onCancelButton`, `onGamepadDirection`, `onSecondaryButton`, `onOptionsButton`, `onMenuButton`); [`Kaal31/benderthemes` `src/input.tsx`](https://github.com/Kaal31/benderthemes/blob/main/src/input.tsx) (`onButtonDown` + `preventDefault`/`stopPropagation`, unconsumed B returns to Steam); [`Emiliopg91/decky-plugin-framework` `src/implementations/input.ts`](https://github.com/Emiliopg91/decky-plugin-framework/blob/main/src/implementations/input.ts) (`RegisterForControllerStateChanges` bitmask decoding for shortcuts)
