import { Focusable } from "@decky/ui";
import type { CSSProperties } from "react";
import { t } from "../strings";
import { type Control, controlKind, controlTargets } from "./controls";
import { BOX, type Spot, shapeDef } from "./shapes";

interface Props {
  padName: string;
  shape: string;
  controls: Control[];
  selected: string | null;
  prefix: string;
  onSelect: (key: string) => void;
}

// Box units → percentages of the drawing, and font sizes in container-width units, so the drawing scales with
// the screen and the hotspots stay on their buttons.
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

// The pad in its own shape, one focusable hotspot per control, labelled with the pad's glyph and coloured by
// where its mapping comes from. Focus selects, so moving over the pad with the D-pad updates the detail card.
export function PadDrawing({ padName, shape, controls, selected, prefix, onSelect }: Props) {
  const def = shapeDef(shape);
  const placed = controls.filter((c) => def.spots[c.key]);
  return (
    <Focusable className="mh-pad" role="group" aria-label={t.map.drawing(padName)}>
      <svg viewBox={`0 0 ${BOX.width} ${BOX.height}`} aria-hidden="true">
        {def.outline}
      </svg>
      {placed.map((control) => {
        const on = control.key === selected;
        return (
          <Focusable
            key={control.key}
            className={`mh-spot${on ? " mh-on" : ""}`}
            data-kind={controlKind(control)}
            style={spotStyle(def.spots[control.key], control.glyph)}
            role="button"
            aria-pressed={on}
            aria-label={spotLabel(control, prefix)}
            focusClassName="mh-focus"
            noFocusRing
            preferredFocus={on}
            onActivate={() => onSelect(control.key)}
            onClick={() => onSelect(control.key)}
            onGamepadFocus={() => onSelect(control.key)}
            onOKActionDescription={t.map.select}
          >
            {control.glyph}
          </Focusable>
        );
      })}
    </Focusable>
  );
}
