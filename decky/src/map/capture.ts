import { GamepadButton } from "@decky/ui";

// Catching the next press for "Change button" (docs/08 Flow 2, "Input capture vs UI navigation").
//
// First source: SteamClient.Input.RegisterForControllerInputMessages(controllerIndex, button, pressed), Steam's
// per-controller button events in a positional layout (A south, B east, X west, Y north) with stick directions and
// back buttons; the button numbers are @decky/ui's ControllerInputGamepadButton (decky-frontend-lib
// src/globals/steam-client/Input.ts @ 10b929d). The Deck's Steam client of 2026-10-23 has it and no longer has
// RegisterForControllerStateChanges, which older clients had (the raw state below). The enum has no right-stick
// directions: a right-stick push for a C button comes from the state API or the UI fallback only. [VERIFY] that
// external pads report through it, and their back buttons.
//
// Older clients: SteamClient.Input.RegisterForControllerStateChanges, Steam's raw state per controller. ulButtons
// and ulUpperButtons use the bit layout of the Steam Deck's HID report (SDL release-2.30.0
// src/joystick/hidapi/SDL_hidapi_steamdeck.c L38-62: R2 0x1, L2 0x2, R1 0x4, L1 0x8, Y 0x10, B 0x20, X 0x40, A 0x80,
// D-pad up/right/left/down 0x100-0x800, View 0x1000, Steam 0x2000, Menu 0x4000, L5 0x8000, R5 0x10000, L3 0x400000,
// R3 0x4000000; upper word L4 0x200, R4 0x400, QAM 0x40000), as a community plugin decodes them for shortcuts
// (Emiliopg91/decky-plugin-framework src/types/input.ts @ f69b374). Stick Y is positive up: SDL negates it for its
// own axes (same file, L305-311).
//
// Fallback: the UI event on the focused element (onButtonDown), which every pad sends but which is Steam's UI
// action, after Steam Input's UI mapping. It's used only if neither API reports the press within 150 ms.

// ControllerInputGamepadButton -> canonical input. Paddles as SDL numbers the Deck's (data/glyphs.json): the
// lower back buttons L5/R5 are LBACK/RBACK, the upper L4/R4 LBACK_UPPER/RBACK_UPPER.
const MESSAGE: Record<number, string> = {
  0: "face_south", 1: "face_east", 2: "face_west", 3: "face_north", 4: "dpad_up", 5: "dpad_right", 6: "dpad_down",
  7: "dpad_left", 8: "start", 9: "select", 20: "ls_up", 21: "ls_down", 22: "ls_left", 23: "ls_right", 25: "l3",
  28: "l2", 29: "r2", 30: "l1", 31: "r1", 32: "paddle4", 33: "paddle3", 34: "guide", 35: "select", 36: "start",
  41: "r3", 44: "paddle2", 45: "paddle1",
};

const LOWER: Record<number, string> = {
  0: "r2", 1: "l2", 2: "r1", 3: "l1", 4: "face_north", 5: "face_east", 6: "face_west", 7: "face_south",
  8: "dpad_up", 9: "dpad_right", 10: "dpad_left", 11: "dpad_down", 12: "select", 13: "guide", 14: "start",
  15: "paddle4", 16: "paddle3", 22: "l3", 26: "r3",
};
const UPPER: Record<number, string> = { 9: "paddle2", 10: "paddle1", 18: "qam" };

const UI: Partial<Record<GamepadButton, string>> = {
  [GamepadButton.OK]: "face_south", [GamepadButton.CANCEL]: "face_east", [GamepadButton.SECONDARY]: "face_west",
  [GamepadButton.OPTIONS]: "face_north", [GamepadButton.BUMPER_LEFT]: "l1", [GamepadButton.BUMPER_RIGHT]: "r1",
  [GamepadButton.TRIGGER_LEFT]: "l2", [GamepadButton.TRIGGER_RIGHT]: "r2", [GamepadButton.DIR_UP]: "dpad_up",
  [GamepadButton.DIR_DOWN]: "dpad_down", [GamepadButton.DIR_LEFT]: "dpad_left", [GamepadButton.DIR_RIGHT]: "dpad_right",
  [GamepadButton.SELECT]: "select", [GamepadButton.START]: "start", [GamepadButton.LSTICK_CLICK]: "l3",
  [GamepadButton.RSTICK_CLICK]: "r3", [GamepadButton.REAR_LEFT_UPPER]: "paddle2",
  [GamepadButton.REAR_LEFT_LOWER]: "paddle4", [GamepadButton.REAR_RIGHT_UPPER]: "paddle1",
  [GamepadButton.REAR_RIGHT_LOWER]: "paddle3",
};

const PUSH = 0.6 * 32767; // a stick or trigger counts as pressed past 60% of its travel

// What the capture is for: a button target takes buttons, triggers and stick directions; an axis target takes a
// stick (its _x or _y) or, for an analog trigger target, a trigger.
export type Want = "button" | "stick-x" | "stick-y" | "trigger";

interface State {
  ulButtons: number;
  ulUpperButtons: number;
  sLeftStickX: number;
  sLeftStickY: number;
  sRightStickX: number;
  sRightStickY: number;
  sTriggerL: number;
  sTriggerR: number;
}

// Everything held in one state, as canonical inputs (docs/03): buttons, stick directions, triggers past PUSH.
function held(s: State): Set<string> {
  const out = new Set<string>();
  const lower = s.ulButtons >>> 0;
  const upper = s.ulUpperButtons >>> 0;
  for (const [bit, name] of Object.entries(LOWER)) if (lower & (1 << Number(bit))) out.add(name);
  for (const [bit, name] of Object.entries(UPPER)) if (upper & (1 << Number(bit))) out.add(name);
  const stick = (side: "ls" | "rs", x: number, y: number) => {
    if (Math.max(Math.abs(x), Math.abs(y)) < PUSH) return;
    out.add(Math.abs(x) > Math.abs(y) ? `${side}_${x > 0 ? "right" : "left"}` : `${side}_${y > 0 ? "up" : "down"}`);
  };
  stick("ls", s.sLeftStickX, s.sLeftStickY);
  stick("rs", s.sRightStickX, s.sRightStickY);
  if (s.sTriggerL > PUSH) out.add("l2");
  if (s.sTriggerR > PUSH) out.add("r2");
  return out;
}

// A held input as what a binding of `want` takes, or null when it doesn't fit (a button for a stick target).
export function asSource(input: string, want: Want): string | null {
  const stick = input.match(/^(ls|rs)_(up|down|left|right)$/);
  if (want === "button") return input;
  if (want === "trigger") return input === "l2" || input === "r2" ? input : null;
  if (!stick) return null;
  return `${stick[1]}_${want === "stick-x" ? "x" : "y"}`;
}

export interface Capture {
  stop: () => void;
  // The UI event of the focused capture element: used when the controller state doesn't say what was pressed.
  uiButton: (button: number) => void;
}

// Calls onPress once with the first input pressed after `armMs` that fits `want` (inputs already held when the
// capture starts must be let go first), or with a non-fitting input so the caller can say why it can't be used.
export function capture(want: Want, onPress: (input: string, fits: boolean) => void, armMs = 250): Capture {
  const start = Date.now();
  const before = new Map<number, Set<string>>();
  let done = false;
  let fallback: ReturnType<typeof setTimeout> | null = null;

  // What caught the last press, for checking a pad on the Deck (window.mhLastCapture in Steam's debugger).
  const finish = (input: string, source = "state", raw?: number) => {
    if (done) return;
    done = true;
    (window as unknown as Record<string, unknown>).mhLastCapture = { input, source, raw, want, at: Date.now() };
    if (fallback) clearTimeout(fallback);
    registration?.unregister();
    onPress(input, asSource(input, want) !== null);
  };

  let registration: { unregister: () => void } | null = null;
  const input = SteamClient.Input as unknown as Record<string, unknown>;
  try {
    if (typeof input.RegisterForControllerInputMessages === "function") {
      registration = (input.RegisterForControllerInputMessages as (
        cb: (index: number, button: number, pressed: boolean) => void) => { unregister: () => void })(
        (_index, button, pressed) => {
          const name = MESSAGE[button];
          if (pressed && name && name !== "guide" && Date.now() - start >= armMs) finish(name, "messages", button);
        });
    } else registration = SteamClient.Input.RegisterForControllerStateChanges((changes: State[]) => {
      for (const change of changes as (State & { unControllerIndex: number })[]) {
        const now = held(change);
        const was = before.get(change.unControllerIndex);
        before.set(change.unControllerIndex, now);
        if (!was || Date.now() - start < armMs) continue; // the first state of each pad is the baseline
        const fresh = [...now].filter((i) => !was.has(i) && i !== "guide" && i !== "qam");
        // A trigger pulled past PUSH also sets its digital bit later; a stick direction wins over nothing.
        const pick = fresh.find((i) => asSource(i, want) !== null) ?? fresh[0];
        if (pick) finish(pick);
      }
    });
  } catch (e) {
    console.warn("map-helper: no controller state; capturing from UI events only", e);
  }

  return {
    stop: () => {
      done = true;
      if (fallback) clearTimeout(fallback);
      registration?.unregister();
    },
    uiButton: (button: number) => {
      const input = UI[button as GamepadButton];
      if (!input || done || Date.now() - start < armMs) return;
      // Give the controller state a moment to report the same press with its physical position first.
      if (!fallback) fallback = setTimeout(() => finish(input, "ui", button), 150);
    },
  };
}
