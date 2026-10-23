import type { ReactNode } from "react";
import { colors } from "../styles";

// The console's own pad, drawn so the edit flow can light the console input being changed ("which N64 button?").
// Our own drawings, like the pads in shapes.tsx: an outline (decoration) and a spot per console input, keyed by
// the input's name in data/layouts/<system>.json; both axes of a stick are one spot. Same 640x400 box as shapes.
// A system with no drawing here gets none, and the flow names the input in words only.

type Spot = { x: number; y: number; r: number; label: string; tint?: string };

interface ConsoleDef {
  outline: ReactNode;
  spots: Record<string, Spot>;
  alias?: Record<string, string>; // layout input -> spot, where several inputs are one thing on the pad
}

const BODY = { fill: colors.surface, stroke: colors.border, strokeWidth: 2 };
const WELL = { fill: "#121820", stroke: colors.border, strokeWidth: 2 };

// The N64 pad: three grips, the D-pad on the left, the stick in the middle (Z is the trigger behind it), A, B and
// the four C buttons on the right, L and R on the shoulders. Colours as on the pad: A blue, B green, C yellow.
const N64_BODY =
  "M90 92 Q320 52 550 92 Q614 106 608 178 L590 322 Q580 368 536 368 Q496 366 488 324 L468 238 Q430 216 402 242 " +
  "L376 334 Q362 380 320 380 Q278 380 264 334 L238 242 Q210 216 172 238 L152 324 Q144 366 104 368 Q60 368 50 322 " +
  "L32 178 Q26 106 90 92 Z";

const N64: ConsoleDef = {
  outline: (
    <>
      <path d={N64_BODY} {...BODY} />
      <path d="M103 126 h24 v22 h22 v24 h-22 v22 h-24 v-22 h-22 v-24 h22 Z" {...WELL} />
      <circle cx={320} cy={262} r={36} {...WELL} />
      <circle cx={532} cy={150} r={56} fill="#151c26" stroke="#2a3644" strokeWidth={2} />
    </>
  ),
  spots: {
    l: { x: 120, y: 44, r: 22, label: "L" },
    r: { x: 520, y: 44, r: 22, label: "R" },
    up: { x: 115, y: 116, r: 15, label: "▲" },
    down: { x: 115, y: 204, r: 15, label: "▼" },
    left: { x: 71, y: 160, r: 15, label: "◀" },
    right: { x: 159, y: 160, r: 15, label: "▶" },
    start: { x: 320, y: 152, r: 19, label: "S", tint: "#e0605a" },
    stick: { x: 320, y: 262, r: 26, label: "◎" },
    z: { x: 320, y: 340, r: 19, label: "Z" },
    b: { x: 420, y: 168, r: 21, label: "B", tint: "#5fc27a" },
    a: { x: 458, y: 214, r: 22, label: "A", tint: "#4f8fe8" },
    c_up: { x: 532, y: 112, r: 16, label: "▲", tint: "#e8c64f" },
    c_down: { x: 532, y: 188, r: 16, label: "▼", tint: "#e8c64f" },
    c_left: { x: 494, y: 150, r: 16, label: "◀", tint: "#e8c64f" },
    c_right: { x: 570, y: 150, r: 16, label: "▶", tint: "#e8c64f" },
  },
};

// The GameCube pad: the main stick top left over the D-pad, START in the middle, the big green A with B, X and Y
// around it, the yellow C stick below them, L and R on the shoulders and Z in front of R. Colours as on the pad.
const GC_BODY =
  "M120 96 Q320 70 520 96 Q600 108 612 190 L600 300 Q590 360 540 360 Q500 358 486 316 L462 262 Q320 240 178 262 " +
  "L154 316 Q140 358 100 360 Q50 360 40 300 L28 190 Q40 108 120 96 Z";

const GC: ConsoleDef = {
  outline: (
    <>
      <path d={GC_BODY} {...BODY} />
      <circle cx={170} cy={160} r={40} {...WELL} />
      <path d="M193 236 h24 v26 h26 v24 h-26 v26 h-24 v-26 h-26 v-24 h26 Z" {...WELL} />
      <circle cx={440} cy={282} r={32} {...WELL} />
    </>
  ),
  spots: {
    l: { x: 130, y: 46, r: 24, label: "L" },
    r: { x: 510, y: 46, r: 24, label: "R" },
    z: { x: 556, y: 92, r: 17, label: "Z", tint: "#8a6fe0" },
    main: { x: 170, y: 160, r: 28, label: "◎" },
    up: { x: 205, y: 246, r: 12, label: "▲" },
    down: { x: 205, y: 302, r: 12, label: "▼" },
    left: { x: 177, y: 274, r: 12, label: "◀" },
    right: { x: 233, y: 274, r: 12, label: "▶" },
    start: { x: 320, y: 172, r: 15, label: "S" },
    a: { x: 470, y: 172, r: 30, label: "A", tint: "#3fb36a" },
    b: { x: 414, y: 222, r: 18, label: "B", tint: "#e0605a" },
    x: { x: 532, y: 150, r: 19, label: "X" },
    y: { x: 460, y: 112, r: 18, label: "Y" },
    c: { x: 440, y: 282, r: 22, label: "C", tint: "#e8c64f" },
  },
  alias: { l_digital: "l", l_analog: "l", r_digital: "r", r_analog: "r" },
};

// The DualShock (PS1) and DualShock 2: D-pad left, △ ○ ✕ □ right in their colours, SELECT, START and ANALOG between
// them, two sticks below, L1/L2 and R1/R2 on the shoulders. A stick's click lights the stick.
const DUALSHOCK_BODY =
  "M150 84 Q320 64 490 84 Q560 92 585 164 L620 300 Q635 362 585 377 Q545 387 515 342 L470 287 Q320 267 170 287 " +
  "L125 342 Q95 387 55 377 Q5 362 20 300 L55 164 Q80 92 150 84 Z";

const DUALSHOCK: ConsoleDef = {
  outline: (
    <>
      <path d={DUALSHOCK_BODY} {...BODY} />
      <path d="M137 113 h26 v34 h34 v26 h-34 v34 h-26 v-34 h-34 v-26 h34 Z" {...WELL} />
      <circle cx={490} cy={160} r={70} fill="#151c26" stroke="#2a3644" strokeWidth={2} />
      <circle cx={240} cy={262} r={38} {...WELL} />
      <circle cx={400} cy={262} r={38} {...WELL} />
    </>
  ),
  spots: {
    l2: { x: 150, y: 22, r: 18, label: "L2" },
    l1: { x: 150, y: 62, r: 18, label: "L1" },
    r2: { x: 490, y: 22, r: 18, label: "R2" },
    r1: { x: 490, y: 62, r: 18, label: "R1" },
    up: { x: 150, y: 128, r: 13, label: "▲" },
    down: { x: 150, y: 192, r: 13, label: "▼" },
    left: { x: 118, y: 160, r: 13, label: "◀" },
    right: { x: 182, y: 160, r: 13, label: "▶" },
    select: { x: 266, y: 160, r: 14, label: "SEL" },
    start: { x: 374, y: 160, r: 14, label: "ST" },
    analog: { x: 320, y: 204, r: 12, label: "AN", tint: "#e0605a" },
    triangle: { x: 490, y: 116, r: 20, label: "△", tint: "#4fc3a1" },
    circle: { x: 534, y: 160, r: 20, label: "○", tint: "#e0605a" },
    cross: { x: 490, y: 204, r: 20, label: "✕", tint: "#6c9be8" },
    square: { x: 446, y: 160, r: 20, label: "□", tint: "#d77bbd" },
    lstick: { x: 240, y: 262, r: 28, label: "L" },
    rstick: { x: 400, y: 262, r: 28, label: "R" },
  },
  alias: { l3: "lstick", r3: "rstick" },
};

const CONSOLES: Record<string, ConsoleDef> = { n64: N64, gc: GC, psx: DUALSHOCK, ps2: DUALSHOCK };

// "n64.standard.c_down" -> "c_down"; a stick axis ("stick_x") -> its stick ("stick"); then the console's alias
// ("gc.standard.l_analog" -> "l").
export function spotOf(target: string, def?: ConsoleDef): string {
  const name = target.split(".").pop()!.replace(/_(x|y)$/, "");
  return def?.alias?.[name] ?? name;
}

export function hasConsolePad(system: string): boolean {
  return system in CONSOLES;
}

// The console pad with `lit` (targets) highlighted, or null when there is no drawing for the system.
export function ConsolePad({ system, lit, label }: { system: string; lit: string[]; label: string }) {
  const def = CONSOLES[system];
  if (!def) return null;
  const on = new Set(lit.map((target) => spotOf(target, def)));
  return (
    <svg className="mh-console" viewBox="0 0 640 400" role="img" aria-label={label}>
      {def.outline}
      {Object.entries(def.spots).map(([name, s]) => {
        const lit = on.has(name);
        return (
          <g key={name}>
            {lit && <circle cx={s.x} cy={s.y} r={s.r + 9} fill="none" stroke={colors.selected} strokeWidth={4} />}
            <circle cx={s.x} cy={s.y} r={s.r} fill={lit ? colors.selected : "#121820"}
              stroke={lit ? colors.selected : s.tint ?? colors.border} strokeWidth={lit ? 3 : 2.5} />
            <text x={s.x} y={s.y} textAnchor="middle" dominantBaseline="central" fontWeight={700}
              fontSize={s.label.length > 1 ? s.r * 0.8 : s.r * 1.05} fill={lit ? colors.onAccent : s.tint ?? colors.text}>
              {s.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// One console input as a small icon, drawn from its spot on the console's drawing (same colour and label), for the
// list rows, the card and the decide screen. null when the system has no drawing or the input no spot.
export function ConsoleIcon({ system, target, size = 22 }: { system: string; target: string; size?: number }) {
  const def = CONSOLES[system];
  const s = def?.spots[spotOf(target, def)];
  if (!s) return null;
  const v = s.r + 3;
  return (
    <svg className="mh-console-icon" width={size} height={size} viewBox={`${-v} ${-v} ${2 * v} ${2 * v}`} aria-hidden="true">
      <circle r={s.r} fill="#121820" stroke={s.tint ?? colors.border} strokeWidth={2.5} />
      <text textAnchor="middle" dominantBaseline="central" fontWeight={700}
        fontSize={s.label.length > 1 ? s.r * 0.8 : s.r * 1.05} fill={s.tint ?? colors.text}>
        {s.label}
      </text>
    </svg>
  );
}

// Icons for a list of console targets, one per spot (a stick's two axes are one icon), when every target has one;
// else null, and the caller writes the labels in words.
export function consoleIcons(system: string, targets: string[], size?: number): ReactNode | null {
  const def = CONSOLES[system];
  if (!def || !targets.length) return null;
  const spots = [...new Set(targets.map((t) => spotOf(t, def)))];
  if (!spots.every((name) => name in def.spots)) return null;
  const first = new Map(targets.map((t) => [spotOf(t, def), t] as const));
  return (
    <span className="mh-console-icons">
      {spots.map((name) => <ConsoleIcon key={name} system={system} target={first.get(name)!} size={size} />)}
    </span>
  );
}

