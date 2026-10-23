import { GamepadButton } from "@decky/ui";

// Catching the next press for "Change button" (docs/08 Flow 2, "Input capture vs UI navigation").
//
// First source: SteamClient.Input.RegisterForControllerInputMessages(controllerIndex, button, pressed), Steam's
// per-controller button events in a positional layout (A south, B east, X west, Y north) with stick directions and
// back buttons; the button numbers are @decky/ui's ControllerInputGamepadButton (decky-frontend-lib
// src/globals/steam-client/Input.ts @ 10b929d). The Deck's Steam client of 2026-10-23 has it and no longer has
// RegisterForControllerStateChanges, which older clients had (the raw state below). The enum has no right-stick
// directions; the right stick comes through SteamClient.Input.RegisterForControllerAnalogInputMessages instead, once
// EnableControllerAnalogInputMessages(true) is on. Its callback is (controllerIndex, kind, down, x, y), not the
// message array decky-frontend-lib types, and Steam's UI reports the right stick as kind 47, ANALOG_SCROLL (the
// right stick scrolls in Big Picture): FAILINATOR5000/decky-cheevodeck src/components/memories/rightStick.ts
// @ main, read 2026-10-23. x and y are a scroll position that keeps moving while the stick is held (about 9 per
// message at full tilt), not the stick's deflection; pushing up makes y fall (a DualSense on the owner's Deck,
// 2026-10-23). So a push is the distance moved since the capture armed.
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
const ANALOG_SCROLL = 47; // the right stick, in the analog messages
const SCROLL_PUSH = 60; // scroll distance that counts as a deliberate push (about 100 ms at full tilt)
const SCROLL_REST_MS = 200; // no message for this long: the stick is back in the centre

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

// Steam's controllers, as its ControllerStore global lists them: the index the input messages carry, VID:PID and
// name. Read in place; nothing about a pad leaves the page.
interface SteamPad {
  nControllerIndex: number;
  unVendorID: number;
  unProductID: number;
  strName: string;
}

function steamPads(): SteamPad[] {
  try {
    return (window as unknown as { ControllerStore?: { GetControllers(): SteamPad[] } }).ControllerStore?.GetControllers() ?? [];
  } catch {
    return [];
  }
}

const hex = (n: number) => n.toString(16).padStart(4, "0");

// The Steam controller indices of the pad with this VID:PID (two of one model are both accepted: Steam's list doesn't
// say which one a player is). null: no way to tell, so any pad counts.
export function padIndices(vidPid: string | null | undefined): number[] | null {
  if (!vidPid) return null;
  const found = steamPads().filter((c) => `${hex(c.unVendorID)}:${hex(c.unProductID)}` === vidPid.toLowerCase());
  return found.length ? found.map((c) => c.nControllerIndex) : null;
}

export function steamPadName(index: number): string | null {
  return steamPads().find((c) => c.nControllerIndex === index)?.strName ?? null;
}

export interface Capture {
  stop: () => void;
  // The UI event of the focused capture element: used when the controller state doesn't say what was pressed.
  uiButton: (button: number) => void;
}

// Calls onPress once with the first input pressed after `armMs` that fits `want` (inputs already held when the
// capture starts must be let go first), or with a non-fitting input so the caller can say why it can't be used.
// pads: the Steam controller indices to listen to (padIndices), or null for any. A press on another pad calls onOther
// with its index and isn't taken.
export function capture(want: Want, onPress: (input: string, fits: boolean) => void,
  { pads = null, onOther }: { pads?: number[] | null; onOther?: (index: number) => void } = {}, armMs = 400): Capture {
  const mine = (index: number) => pads === null || pads.includes(index);
  const start = Date.now();
  const before = new Map<number, Set<string>>();
  let done = false;
  let fallback: ReturnType<typeof setTimeout> | null = null;

  // What caught each press, for checking a pad on the Deck (window.mhCaptures in Steam's debugger, the last 20).
  const finish = (input: string, source = "state", raw?: number, more: Record<string, unknown> = {}) => {
    if (done) return;
    done = true;
    const seen = ((window as unknown as Record<string, unknown>).mhCaptures ??= []) as unknown[];
    seen.push({ input, source, raw, want, at: Date.now(), ...more });
    seen.splice(0, Math.max(0, seen.length - 20));
    if (fallback) clearTimeout(fallback);
    release();
    onPress(input, asSource(input, want) !== null);
  };
  const release = () => {
    registration?.unregister();
    if (analog) {
      analog.unregister();
      (SteamClient.Input as unknown as { EnableControllerAnalogInputMessages?: (on: boolean) => void })
        .EnableControllerAnalogInputMessages?.(false);
    }
  };

  let registration: { unregister: () => void } | null = null;
  let analog: { unregister: () => void } | null = null;
  const scroll = new Map<number, { x: number; y: number; at: number; x0: number; y0: number; early: boolean }>();
  const down = new Set<string>();
  const input = SteamClient.Input as unknown as Record<string, unknown>;
  const messages = typeof input.RegisterForControllerInputMessages === "function";
  try {
    if (messages) {
      registration = (input.RegisterForControllerInputMessages as (
        cb: (index: number, button: number, pressed: boolean) => void) => { unregister: () => void })(
        (index, button, pressed) => {
          // A button seen held before the capture armed (the A that opened it, and its repeats) only counts again
          // after it's released.
          const key = `${index}:${button}`;
          if (!pressed) down.delete(key);
          else if (Date.now() - start < armMs) down.add(key);
          else if (!down.has(key) && MESSAGE[button] && MESSAGE[button] !== "guide") {
            if (mine(index)) finish(MESSAGE[button], "messages", button, { index });
            else onOther?.(index);
          }
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
  try {
    if (typeof input.RegisterForControllerAnalogInputMessages === "function"
        && typeof input.EnableControllerAnalogInputMessages === "function") {
      const log = ((window as unknown as Record<string, unknown>).mhAnalogLog = []) as unknown[];
      analog = (input.RegisterForControllerAnalogInputMessages as (
        cb: (index: number, kind: number, down: boolean, x: number, y: number) => void) => { unregister: () => void })(
        (index, kind, _down, x, y) => {
          if (log.length < 40) log.push({ index, kind, x, y });
          if (kind !== ANALOG_SCROLL || typeof x !== "number" || typeof y !== "number" || done || !mine(index)) return;
          const now = Date.now();
          const was = scroll.get(index);
          // A new push starts after a rest; one already going when the capture opened counts only after a rest.
          if (!was || now - was.at > SCROLL_REST_MS) {
            scroll.set(index, { x, y, at: now, x0: x, y0: y, early: now - start < armMs });
            return;
          }
          Object.assign(was, { x, y, at: now });
          if (was.early) return;
          const [dx, dy] = [x - was.x0, y - was.y0];
          if (Math.max(Math.abs(dx), Math.abs(dy)) < SCROLL_PUSH) return;
          finish(Math.abs(dx) > Math.abs(dy) ? `rs_${dx > 0 ? "right" : "left"}` : `rs_${dy < 0 ? "up" : "down"}`,
            "analog", kind, { index, dx: Math.round(dx), dy: Math.round(dy) });
        });
      (input.EnableControllerAnalogInputMessages as (on: boolean) => void)(true);
    }
  } catch (e) {
    console.warn("map-helper: no analog input messages; the right stick can't be captured", e);
  }

  return {
    stop: () => {
      done = true;
      if (fallback) clearTimeout(fallback);
      release();
    },
    uiButton: (button: number) => {
      const input = UI[button as GamepadButton];
      // The UI event doesn't say which pad sent it: with the input messages there (they do), it's left to them.
      if (!input || done || Date.now() - start < armMs || (messages && pads !== null)) return;
      // Give the controller state a moment to report the same press with its physical position first.
      if (!fallback) fallback = setTimeout(() => finish(input, "ui", button), 150);
    },
  };
}
