import { Focusable, type GamepadEvent } from "@decky/ui";
import type { ReactNode } from "react";
import { FaUndoAlt } from "react-icons/fa";
import type { Pad, PadInput } from "../data";
import { Glyph } from "../glyphs";
import { t } from "../strings";
import { steamKey, steamOnlyTitle } from "./BackStrip";
import { type Control, controlKind, controlNote, controlTargets, summarizeTargets } from "./controls";
import { spotLabel } from "./PadDrawing";

// The key the "Back to emulator defaults" row selects: no control has it.
export const DEFAULTS_KEY = "mh:defaults";

interface Props {
  pad: Pad;
  controls: Control[];
  steamOnly: PadInput[];
  isDeck: boolean;
  selected: string | null;
  prefix: string;
  onSelect: (key: string) => void;
  onChange?: (control: Control) => void; // A on a row
  onDefault?: (control: Control) => void; // X on a row, where canDefault says one of the user's rules sets something
  canDefault?: (control: Control) => boolean;
  defaults?: { note: string | null; onActivate: () => void }; // the "Back to emulator defaults" row, when rules apply
}

// The focused row scrolls itself into view. Not a ScrollPanelGroup: Steam's group takes focus itself (a grey box
// around the whole list, footer "Select") when a modal closes, instead of the row you were on.
const reveal = (evt: GamepadEvent) => (evt.target as HTMLElement | null)?.scrollIntoView?.({ block: "nearest" });

// Steam's nav options that @decky/ui doesn't type. A node's onMove* runs only when moving among its own children
// found nothing in that direction, and true ends the move there (the client's CFocusNavNode.OnNavigationEvent,
// read on the Deck 2026-10-23). On the list that's its ends: up on the first row used to reach the top bar's
// search field, which is collapsed to an icon. Moves between rows never reach it, unlike onGamepadDirection.
const stay = () => true;
const keepFocusIn = { onMoveUp: stay, onMoveDown: stay, onMoveLeft: stay, onMoveRight: stay } as object;
// autoFocus: the row takes focus when the page mounts, instead of the top bar's search field keeping it (opening
// the map from the Quick Access menu left focus there).
const autoFocus = (on: boolean) => ({ autoFocus: on }) as object;

function Row({ id, on, label, onSelect, onActivate, onSecondary, okText, secondaryText, children }: {
  id: string;
  on: boolean;
  label: string;
  onSelect: (key: string) => void;
  onActivate?: () => void;
  onSecondary?: () => void;
  okText?: string;
  secondaryText?: string;
  children: ReactNode;
}) {
  const activate = () => (onActivate ? onActivate() : onSelect(id));
  return (
    <Focusable
      className={`mh-row${on ? " mh-on" : ""}`}
      role="button"
      aria-pressed={on}
      aria-label={label}
      focusClassName="mh-focus"
      noFocusRing
      preferredFocus={on}
      {...autoFocus(on)}
      onActivate={activate}
      onClick={activate}
      onGamepadFocus={(evt) => {
        onSelect(id);
        reveal(evt);
      }}
      onOKActionDescription={okText ?? t.map.select}
      onSecondaryButton={onSecondary}
      onSecondaryActionDescription={onSecondary ? secondaryText : undefined}
    >
      {children}
    </Focusable>
  );
}

// Every control and what it drives, one row each: the part of the screen the D-pad moves through. Moving onto a
// row selects it, so the drawing and the detail card follow focus. Inputs only Steam sees (back buttons,
// paddles, a touchpad click) come last, under their own heading.
export function ControlList(props: Props) {
  const { pad, controls, steamOnly, isDeck, selected, prefix, onSelect, onChange, onDefault, canDefault, defaults } = props;
  return (
    <div className="mh-list-wrap">
        <Focusable className="mh-list" flow-children="column" role="list" aria-label={t.map.inputs} {...keepFocusIn}>
          {defaults && (
            <Row id={DEFAULTS_KEY} on={selected === DEFAULTS_KEY} label={t.edit.defaultsRow} onSelect={onSelect}
              onActivate={defaults.onActivate} okText={t.edit.defaultsRow}>
              <span className="mh-row-glyph"><FaUndoAlt aria-hidden="true" size={16} /></span>
              <span className="mh-row-target mh-row-defaults">{t.edit.defaultsRow}</span>
              {defaults.note && <span className="mh-row-defaults-note">{defaults.note}</span>}
            </Row>
          )}
          {controls.map((control) => {
            const targets = controlTargets(control);
            const note = controlNote(control);
            return (
              <Row key={control.key} id={control.key} on={control.key === selected}
                label={spotLabel(control, prefix)} onSelect={onSelect}
                onActivate={onChange && (() => onChange(control))}
                okText={targets.length ? t.map.changeButton : t.edit.assign}
                onSecondary={onDefault && canDefault?.(control) ? () => onDefault(control) : undefined}
                secondaryText={t.edit.backToDefault}>
                <span className="mh-row-glyph"><Glyph pad={pad} label={control.glyph} size={22} /></span>
                <span className="mh-row-name">{control.name !== control.glyph ? control.name : ""}</span>
                {targets.length ? (
                  <span className="mh-row-target">{[prefix, summarizeTargets(targets)].filter(Boolean).join(" ")}</span>
                ) : note ? (
                  <span className="mh-row-target mh-row-note" data-kind={controlKind(control)}>{note}</span>
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
              <span className="mh-row-glyph"><Glyph pad={pad} label={input.glyph} size={22} /></span>
              <span className="mh-row-name">{input.name}</span>
              <span className="mh-row-target mh-row-none">{t.map.steamOnly}</span>
              <span className="mh-dot" data-kind="none" aria-hidden="true" />
            </Row>
          ))}
        </Focusable>
    </div>
  );
}
