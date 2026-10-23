import type { ReactNode } from "react";
import type { Shape } from "../data";

// Each pad is drawn in a 640x400 box. A shape has an outline (decoration only) and the spot where each control's
// hotspot sits: [centre x, centre y, width, height], in box units. Controls with no spot on a shape (a Capture
// button on a pad that has none) are still in the list beside the drawing.
export const BOX = { width: 640, height: 400 };

export type Spot = [cx: number, cy: number, w: number, h: number];

interface ShapeDef {
  outline: ReactNode;
  spots: Record<string, Spot>;
}

const BODY = { fill: "#1a2230", stroke: "#33414f", strokeWidth: 2 };
const WELL = { fill: "#121820", stroke: "#33414f", strokeWidth: 2 };
const PANEL = { fill: "#151c26", stroke: "#33414f", strokeWidth: 2 };

// A plus-shaped d-pad well centred on (cx, cy), arm width `a`.
function Cross({ cx, cy, a }: { cx: number; cy: number; a: number }) {
  const x = cx - a / 2;
  const y = cy - (a * 3) / 2;
  return <path d={`M${x} ${y} h${a} v${a} h${a} v${a} h${-a} v${a} h${-a} v${-a} h${-a} v${-a} h${a} Z`} {...WELL} />;
}

const SYMMETRIC_BODY =
  "M150 74 Q320 54 490 74 Q560 82 585 154 L620 300 Q635 362 585 377 Q545 387 515 342 L470 277 Q320 257 170 277 " +
  "L125 342 Q95 387 55 377 Q5 362 20 300 L55 154 Q80 82 150 74 Z";

const OFFSET_BODY =
  "M140 82 Q320 64 500 82 Q568 90 592 162 L622 288 Q634 356 590 373 Q548 386 516 344 L478 288 Q320 270 162 288 " +
  "L124 344 Q92 386 50 373 Q6 356 18 288 L48 162 Q72 90 140 82 Z";

const DECK_BODY =
  "M40 92 H600 Q632 92 634 130 L636 300 Q636 336 604 342 L560 348 Q520 352 498 330 H142 Q120 352 80 348 " +
  "L36 342 Q4 336 4 300 L6 130 Q8 92 40 92 Z";

const SHOULDERS_WIDE: Record<string, Spot> = {
  l2: [150, 22, 80, 36],
  r2: [490, 22, 80, 36],
  l1: [150, 60, 80, 32],
  r1: [490, 60, 80, 32],
};

const PLAYSTATION_SPOTS: Record<string, Spot> = {
  ...SHOULDERS_WIDE,
  face_south: [490, 204, 40, 40],
  face_east: [534, 162, 40, 40],
  face_west: [446, 162, 40, 40],
  face_north: [490, 120, 40, 40],
  dpad: [150, 160, 64, 44],
  select: [214, 104, 68, 32],
  start: [426, 104, 72, 32],
  touchpad: [320, 124, 104, 40],
  guide: [320, 214, 40, 32],
  misc1: [320, 250, 48, 26],
  ls: [235, 245, 56, 56],
  rs: [405, 245, 56, 56],
};

const XBOX_SPOTS: Record<string, Spot> = {
  l2: [140, 22, 80, 36],
  r2: [500, 22, 80, 36],
  l1: [140, 60, 80, 32],
  r1: [500, 60, 80, 32],
  face_south: [480, 200, 40, 40],
  face_east: [522, 160, 40, 40],
  face_west: [438, 160, 40, 40],
  face_north: [480, 120, 40, 40],
  dpad: [250, 245, 64, 44],
  select: [262, 140, 64, 32],
  start: [378, 140, 64, 32],
  misc1: [320, 140, 40, 28],
  guide: [320, 96, 40, 36],
  ls: [170, 155, 56, 56],
  rs: [390, 245, 56, 56],
};

const SHAPES: Record<Shape, ShapeDef> = {
  playstation: {
    outline: (
      <>
        <path d={SYMMETRIC_BODY} {...BODY} />
        <rect x={250} y={80} width={140} height={84} rx={12} {...PANEL} />
        <path d="M262 82 Q320 76 378 82" fill="none" stroke="#4a6a8a" strokeWidth={3} strokeLinecap="round" />
        <circle cx={235} cy={245} r={38} {...WELL} />
        <circle cx={405} cy={245} r={38} {...WELL} />
        <circle cx={320} cy={214} r={12} {...WELL} />
        <Cross cx={150} cy={160} a={24} />
      </>
    ),
    spots: PLAYSTATION_SPOTS,
  },
  xbox: {
    outline: (
      <>
        <path d={OFFSET_BODY} {...BODY} />
        <circle cx={320} cy={96} r={16} {...PANEL} />
        <circle cx={480} cy={160} r={62} fill="#151c26" stroke="#2a3644" strokeWidth={2} />
        <circle cx={170} cy={155} r={38} {...WELL} />
        <circle cx={390} cy={245} r={38} {...WELL} />
        <Cross cx={250} cy={245} a={24} />
      </>
    ),
    spots: XBOX_SPOTS,
  },
  // Switch Pro style: offset sticks like the Xbox shape, with Minus/Plus, Home and Capture in the middle.
  nintendo: {
    outline: (
      <>
        <path d={OFFSET_BODY} {...BODY} />
        <circle cx={480} cy={160} r={62} fill="#151c26" stroke="#2a3644" strokeWidth={2} />
        <circle cx={170} cy={155} r={38} {...WELL} />
        <circle cx={390} cy={245} r={38} {...WELL} />
        <Cross cx={250} cy={245} a={24} />
      </>
    ),
    spots: {
      ...XBOX_SPOTS,
      select: [272, 128, 52, 32],
      start: [368, 128, 52, 32],
      guide: [348, 178, 40, 32],
      misc1: [292, 178, 40, 32],
    },
  },
  // The Steam Deck: the screen in the middle, sticks above the trackpads, back buttons drawn in the strip below.
  deck: {
    outline: (
      <>
        <path d={DECK_BODY} {...BODY} />
        <rect x={196} y={110} width={248} height={196} rx={8} fill="#0b1016" stroke="#33414f" strokeWidth={2} />
        <text x={320} y={214} textAnchor="middle" fill="#3d4b5a" fontSize={13}>
          screen
        </text>
        <rect x={44} y={222} width={116} height={96} rx={14} {...PANEL} />
        <rect x={480} y={222} width={116} height={96} rx={14} {...PANEL} />
        <circle cx={150} cy={148} r={28} {...WELL} />
        <circle cx={490} cy={148} r={28} {...WELL} />
        <Cross cx={63} cy={151} a={18} />
      </>
    ),
    spots: {
      l2: [70, 30, 72, 32],
      r2: [570, 30, 72, 32],
      l1: [70, 68, 72, 30],
      r1: [570, 68, 72, 30],
      face_south: [566, 176, 32, 32],
      face_east: [598, 146, 32, 32],
      face_west: [534, 146, 32, 32],
      face_north: [566, 116, 32, 32],
      dpad: [63, 151, 56, 40],
      select: [158, 102, 56, 28],
      start: [482, 102, 56, 28],
      ls: [150, 148, 48, 48],
      rs: [490, 148, 48, 48],
      trackpad_l: [102, 270, 80, 48],
      trackpad_r: [538, 270, 80, 48],
      guide: [180, 318, 48, 22],
      qam: [460, 318, 48, 22],
    },
  },
  // Any other pad: a plain symmetric outline with positional buttons.
  generic: {
    outline: (
      <>
        <path d={SYMMETRIC_BODY} {...BODY} />
        <circle cx={235} cy={245} r={38} {...WELL} />
        <circle cx={405} cy={245} r={38} {...WELL} />
        <circle cx={320} cy={214} r={12} {...WELL} />
        <Cross cx={150} cy={160} a={24} />
      </>
    ),
    spots: PLAYSTATION_SPOTS,
  },
};

export function shapeDef(shape: string): ShapeDef {
  return SHAPES[shape as Shape] ?? SHAPES.generic;
}
