import { Focusable } from "@decky/ui";
import { t } from "../strings";
import { type Control, controlKind, controlTargets, summarizeTargets } from "./controls";
import { spotLabel } from "./PadDrawing";

interface Props {
  controls: Control[];
  selected: string | null;
  prefix: string;
  onSelect: (key: string) => void;
}

// Every control and what it drives, as a column of rows: the same selection as the drawing, with big targets
// for touch and a plain reading order for the D-pad.
export function ControlList({ controls, selected, prefix, onSelect }: Props) {
  return (
    <Focusable className="mh-list" flow-children="column" role="list" aria-label={t.map.inputs}>
      {controls.map((control) => {
        const on = control.key === selected;
        const kind = controlKind(control);
        const targets = controlTargets(control);
        return (
          <Focusable
            key={control.key}
            className={`mh-row${on ? " mh-on" : ""}`}
            role="button"
            aria-pressed={on}
            aria-label={spotLabel(control, prefix)}
            focusClassName="mh-focus"
            noFocusRing
            onActivate={() => onSelect(control.key)}
            onClick={() => onSelect(control.key)}
            onGamepadFocus={() => onSelect(control.key)}
            onOKActionDescription={t.map.select}
          >
            <span className="mh-row-glyph">{control.glyph}</span>
            {targets.length ? (
              <span className="mh-row-target">{[prefix, summarizeTargets(targets)].filter(Boolean).join(" ")}</span>
            ) : (
              <span className="mh-row-target mh-row-none">{t.map.nothing}</span>
            )}
            <span className="mh-dot" data-kind={kind} aria-hidden="true" />
          </Focusable>
        );
      })}
    </Focusable>
  );
}
