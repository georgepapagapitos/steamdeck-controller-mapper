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

const CONSOLES: Record<string, ConsoleDef> = { n64: N64 };

// "n64.standard.c_down" -> "c_down"; a stick axis ("stick_x") -> its stick ("stick").
export function spotOf(target: string): string {
  return target.split(".").pop()!.replace(/_(x|y)$/, "");
}

export function hasConsolePad(system: string): boolean {
  return system in CONSOLES;
}

// The console pad with `lit` (targets) highlighted, or null when there is no drawing for the system.
export function ConsolePad({ system, lit, label }: { system: string; lit: string[]; label: string }) {
  const def = CONSOLES[system];
  if (!def) return null;
  const on = new Set(lit.map(spotOf));
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
