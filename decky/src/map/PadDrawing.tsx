import type { CSSProperties } from "react";
import { t } from "../strings";
import { type Control, controlKind, controlTargets } from "./controls";
import { BOX, type Spot, shapeDef } from "./shapes";

interface Props {
  padName: string;
  shape: string;
  controls: Control[];
  selected: string | null;
}

// Box units → percentages of the drawing, and font sizes in container-width units, so the drawing scales with
// its column and the labels stay on their buttons.
const pctX = (n: number) => `${(n / BOX.width) * 100}%`;
const pctY = (n: number) => `${(n / BOX.height) * 100}%`;
const cq = (n: number) => `${(n / BOX.width) * 100}cqw`;

function spotStyle([cx, cy, w, h]: Spot, glyph: string): CSSProperties {
  return {
    left: pctX(cx - w / 2),
    top: pctY(cy - h / 2),
    width: pctX(w),
    height: pctY(h),
    borderRadius: cq(Math.min(w, h) / 2),
    fontSize: cq(glyph.length > 2 ? 12 : 16),
  };
}

export function spotLabel(control: Control, prefix: string): string {
  const targets = controlTargets(control);
  const what = targets.length ? targets.map((l) => (prefix ? `${prefix} ${l}` : l)).join(", ") : t.map.nothing;
  return `${control.glyph}, ${control.name}: ${what}`;
}

// The pad in its own shape, each control labelled with the pad's glyph and coloured by where its mapping comes
// from. It's a picture, not something to navigate: Steam's D-pad focus can't move reliably between freely placed
// buttons, so the list beside it takes focus and the drawing lights up whichever control the list is on.
export function PadDrawing({ padName, shape, controls, selected }: Props) {
  const def = shapeDef(shape);
  const placed = controls.filter((c) => def.spots[c.key]);
  return (
    <div className="mh-pad" role="img" aria-label={t.map.drawing(padName)}>
      <svg viewBox={`0 0 ${BOX.width} ${BOX.height}`} aria-hidden="true">
        {def.outline}
      </svg>
      {placed.map((control) => (
        <div
          key={control.key}
          className={`mh-spot${control.key === selected ? " mh-on" : ""}`}
          data-kind={controlKind(control)}
          style={spotStyle(def.spots[control.key], control.glyph)}
          aria-hidden="true"
        >
          {control.glyph}
        </div>
      ))}
    </div>
  );
}
