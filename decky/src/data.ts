// The JSON that `map-helper show --json` prints and mh-run writes to $STATE/last-launch.json (schema 1, docs/08
// "The data"). Fields the plugin doesn't need yet are still typed, so the shape is documented in one place.

export type SourceKind = "rule" | "emulator" | "emudeck";

export interface Source {
  kind: SourceKind | string;
  rule_id?: string;
  rule_label?: string;
  scope?: string;
  detail?: string;
}

export interface Drive {
  target: string; // "n64.standard.c_down"
  label: string; // the console's own label: "C▼"
  source: Source;
}

export interface PadInput {
  input: string; // canonical name: face_south, dpad_up, ls_x, paddle1 ...
  glyph: string; // as printed on the pad: ✕, A, L1, Create
  name: string;
  drives: Drive[]; // none (does nothing) or several (a clash, also in warnings)
  note?: string;
  note_short?: string; // a few words for a list row: "Hold for C buttons"
  note_source?: Source; // where the note's fact comes from (EmuDeck's hotkey button, the core's modifier)
  steam_only?: boolean; // back buttons and paddles: emulators never see them
}

export type Shape = "playstation" | "xbox" | "nintendo" | "deck" | "generic";

export interface Pad {
  name: string;
  model?: string | null;
  family?: string | null;
  style?: string | null;
  shape: Shape | string;
  steam_slot?: number | null;
  vid_pid?: string | null; // the physical pad's, "054c:0ce6"; null when it isn't behind Steam
  emulator_port?: number | null;
}

export interface PadOption {
  key: string; // "pak", "deadzones.ls"
  value: string | number | boolean | null;
  label: string;
  source?: Source;
}

export interface Player {
  player: number;
  pad: Pad;
  inputs: PadInput[];
  options?: PadOption[];
}

export type Outcome = "changed" | "no-changes" | "skipped" | "error";

export interface Launch {
  ts: string; // local time, "2026-10-23T10:55:49"
  mode: string; // "es-de", "steam", or "show" for a preview that launched nothing
  emulator: string;
  core?: string | null;
  system: string;
  system_name?: string | null;
  game?: string | null;
  ms?: number | null;
  outcome: Outcome | string;
  detail?: string | null;
}

export interface Policy {
  name: string; // steam-order | external-first | pinned | deck-only
  reason?: string | null;
}

export interface LastLaunch {
  schema: number;
  launch: Launch;
  policy?: Policy | null;
  players: Player[];
  warnings?: unknown[];
}

// What the backend's get_last_launch() returns (main.py). `sample` is only set by fixture builds.
export type ErrorCode = "not-installed" | "no-launch" | "no-python" | "timeout" | "bad-output" | "failed";

export type LastLaunchResult =
  | { ok: true; data: LastLaunch; sample?: boolean }
  | { ok: false; code: ErrorCode | string; error: string; sample?: boolean };
