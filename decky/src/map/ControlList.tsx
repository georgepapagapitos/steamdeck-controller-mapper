import { Focusable, type GamepadEvent, ScrollPanelGroup } from "@decky/ui";
import type { ReactNode } from "react";
import type { PadInput } from "../data";
import { t } from "../strings";
import { steamKey, steamOnlyTitle } from "./BackStrip";
import { type Control, controlKind, controlTargets, summarizeTargets } from "./controls";
import { spotLabel } from "./PadDrawing";

interface Props {
  controls: Control[];
  steamOnly: PadInput[];
  isDeck: boolean;
  selected: string | null;
  prefix: string;
  onSelect: (key: string) => void;
}

// Steam scrolls a ScrollPanelGroup to keep the focused row in view; nudging the row into view as well covers a
// Steam build where the group isn't found (it's looked up in Steam's own modules).
const reveal = (evt: GamepadEvent) => (evt.target as HTMLElement | null)?.scrollIntoView?.({ block: "nearest" });

function Row({ id, on, label, onSelect, children }: {
  id: string;
  on: boolean;
  label: string;
  onSelect: (key: string) => void;
  children: ReactNode;
}) {
  return (
    <Focusable
      className={`mh-row${on ? " mh-on" : ""}`}
      role="button"
      aria-pressed={on}
      aria-label={label}
      focusClassName="mh-focus"
      noFocusRing
      preferredFocus={on}
      onActivate={() => onSelect(id)}
      onClick={() => onSelect(id)}
      onGamepadFocus={(evt) => {
        onSelect(id);
        reveal(evt);
      }}
      onOKActionDescription={t.map.select}
    >
      {children}
    </Focusable>
  );
}

// Every control and what it drives, one row each: the part of the screen the D-pad moves through. Moving onto a
// row selects it, so the drawing and the detail card follow focus. Inputs only Steam sees (back buttons,
// paddles, a touchpad click) come last, under their own heading.
export function ControlList({ controls, steamOnly, isDeck, selected, prefix, onSelect }: Props) {
  const Scroll = ScrollPanelGroup ?? "div";
  return (
    <div className="mh-list-wrap">
      <Scroll>
        <Focusable className="mh-list" flow-children="column" role="list" aria-label={t.map.inputs}>
          {controls.map((control) => {
            const targets = controlTargets(control);
            return (
              <Row key={control.key} id={control.key} on={control.key === selected}
                label={spotLabel(control, prefix)} onSelect={onSelect}>
                <span className="mh-row-glyph">{control.glyph}</span>
                <span className="mh-row-name">{control.name !== control.glyph ? control.name : ""}</span>
                {targets.length ? (
                  <span className="mh-row-target">{[prefix, summarizeTargets(targets)].filter(Boolean).join(" ")}</span>
                ) : (
                  <span className="mh-row-target mh-row-none">{t.map.nothing}</span>
                )}
                <span className="mh-dot" data-kind={controlKind(control)} aria-hidden="true" />
              </Row>
            );
          })}
          {steamOnly.length > 0 && (
            <div className="mh-list-heading">
              <span>{steamOnlyTitle(steamOnly, isDeck)}</span>
              <span className="mh-list-heading-note">{isDeck ? t.map.steamOnlyNoteDeck : t.map.steamOnlyNote}</span>
            </div>
          )}
          {steamOnly.map((input) => (
            <Row key={input.input} id={steamKey(input)} on={steamKey(input) === selected}
              label={`${input.glyph}, ${input.name}: ${t.map.steamOnly}`} onSelect={onSelect}>
              <span className="mh-row-glyph">{input.glyph}</span>
              <span className="mh-row-name">{input.name}</span>
              <span className="mh-row-target mh-row-none">{t.map.steamOnly}</span>
              <span className="mh-dot" data-kind="none" aria-hidden="true" />
            </Row>
          ))}
        </Focusable>
      </Scroll>
    </div>
  );
}
