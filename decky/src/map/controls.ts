import type { Drive, PadInput, SourceKind } from "../data";

// A control is one physical thing on the pad: a button, the d-pad, a stick. The d-pad and each stick carry
// several canonical inputs (dpad_up…, ls_x, ls_y, l3), which the drawing shows as one hotspot and the detail
// card lists one by one. Everything else is a control of its own.
export interface Control {
  key: string; // "face_south", "dpad", "ls"
  glyph: string;
  name: string;
  inputs: PadInput[];
}

const GROUPS: { key: string; glyph: string; name: string; match: (input: string) => boolean }[] = [
  { key: "dpad", glyph: "D-pad", name: "D-pad", match: (i) => i.startsWith("dpad_") },
  { key: "ls", glyph: "L", name: "Left stick", match: (i) => i === "ls" || i.startsWith("ls_") || i === "l3" },
  { key: "rs", glyph: "R", name: "Right stick", match: (i) => i === "rs" || i.startsWith("rs_") || i === "r3" },
  { key: "touchpad", glyph: "Touchpad", name: "Touchpad", match: (i) => i.startsWith("touchpad") },
  { key: "trackpad_l", glyph: "L pad", name: "Left trackpad", match: (i) => i.startsWith("trackpad_l") },
  { key: "trackpad_r", glyph: "R pad", name: "Right trackpad", match: (i) => i.startsWith("trackpad_r") },
];

// Controls in the order their first input appears (the core keeps inputs in a stable order).
// Steam-only inputs (back buttons, paddles) are left out: they get their own strip.
export function groupControls(inputs: PadInput[]): Control[] {
  const controls: Control[] = [];
  const byKey = new Map<string, Control>();
  for (const input of inputs) {
    if (input.steam_only) continue;
    const group = GROUPS.find((g) => g.match(input.input));
    const key = group?.key ?? input.input;
    let control = byKey.get(key);
    if (!control) {
      control = group
        ? { key, glyph: group.glyph, name: group.name, inputs: [] }
        : { key, glyph: input.glyph, name: input.name, inputs: [] };
      byKey.set(key, control);
      controls.push(control);
    }
    control.inputs.push(input);
  }
  // When a group has an input named like it (the core sends a stick as one input, `ls`), that input's glyph and
  // name are the pad's own and read better than the generic ones.
  for (const control of controls) {
    const own = control.inputs.find((i) => i.input === control.key);
    if (own) {
      control.glyph = own.glyph;
      control.name = own.name;
    }
  }
  return controls;
}

export function steamOnlyInputs(inputs: PadInput[]): PadInput[] {
  return inputs
    .filter((i) => i.steam_only)
    .sort((a, b) => a.glyph.localeCompare(b.glyph, undefined, { numeric: true }));
}

export function controlDrives(control: Control): Drive[] {
  return control.inputs.flatMap((i) => i.drives);
}

// The colour of a control: where its mapping came from. The first source wins, since a control usually has one
// (a whole stick comes from one place). A control that drives nothing takes its note's source if it has one
// (Select is EmuDeck's hotkey button), else "none".
export type ControlKind = SourceKind | "none" | "other";

export function kindOf(kind: string | undefined): ControlKind {
  return kind === "rule" || kind === "emulator" || kind === "emudeck" ? kind : "other";
}

export function controlKind(control: Control): ControlKind {
  const first = controlDrives(control)[0];
  if (first) return kindOf(first.source?.kind);
  const noted = control.inputs.find((i) => i.note_source);
  return noted ? kindOf(noted.note_source?.kind) : "none";
}

// "D-pad up, D-pad down" → "D-pad up, down": labels that share a first word say it once.
export function summarizeTargets(labels: string[]): string {
  const first = labels[0]?.split(" ")[0];
  const shared = labels.length > 1 && labels.every((l) => l.startsWith(`${first} `));
  return shared ? `${first} ${labels.map((l) => l.slice(first.length + 1)).join(", ")}` : labels.join(", ");
}

// "C▲ C▼ C◀ C▶": what the control drives, without repeating a label (ls_x and ls_y both say "Stick").
export function controlTargets(control: Control): string[] {
  const labels: string[] = [];
  for (const drive of controlDrives(control)) {
    if (!labels.includes(drive.label)) labels.push(drive.label);
  }
  return labels;
}
