import { DialogButton, Focusable } from "@decky/ui";
import type { Pad, PadInput } from "../data";
import { sourceWords } from "../format";
import { Glyph } from "../glyphs";
import { t } from "../strings";
import { type Control, controlTargets } from "./controls";

interface Props {
  pad: Pad;
  prefix: string;
  control?: Control;
  steamOnly?: PadInput;
  isDeck: boolean;
  onChange?: () => void;
  onDefault?: () => void; // only when one of the user's rules sets something on this control
}

function InputDrives({ input, prefix, showInput }: { input: PadInput; prefix: string; showInput: boolean }) {
  const label = (l: string) => (prefix ? `${prefix} ${l}` : l);
  return (
    <div className="mh-card-drive">
      {showInput && <div className="mh-card-input">{`${input.glyph} · ${input.name}`}</div>}
      {input.drives.length === 0 && <div className="mh-card-target">{t.map.nothingLong}</div>}
      {input.drives.map((drive, i) => (
        <div key={`${drive.target}-${i}`} className="mh-card-drive">
          <div className="mh-card-target">{label(drive.label)}</div>
          <div>
            <span className="mh-badge" data-kind={drive.source?.kind}>
              {sourceWords(drive.source)}
            </span>
          </div>
        </div>
      ))}
      {input.drives.length > 1 && <div className="mh-card-warn">{t.map.clash}</div>}
      {input.note && (
        <div className="mh-card-note" data-kind={input.note_source?.kind}>
          {input.note}
          {input.note_source && <span className="mh-card-note-source">{` (${sourceWords(input.note_source)})`}</span>}
        </div>
      )}
    </div>
  );
}

// The selected control: its glyph and name, what each of its inputs drives, where that came from, and any note,
// with "Change button" (or "Give it a job" when it does nothing) and "Back to default" for what a rule set.
export function DetailCard({ pad, prefix, control, steamOnly, isDeck, onChange, onDefault }: Props) {
  if (steamOnly) {
    return (
      <section className="mh-card" aria-live="polite">
        <div className="mh-card-head">
          <Glyph pad={pad} label={steamOnly.glyph} size={26} className="mh-card-glyph" />
          <span className="mh-card-name">{steamOnly.name}</span>
        </div>
        <div className="mh-card-target">{t.map.steamOnly}</div>
        <div className="mh-card-note">{t.map.steamOnlyDetail}</div>
        <div className="mh-card-note">{isDeck ? t.map.steamOnlyNoteDeck : t.map.steamOnlyNote}</div>
        {steamOnly.note && (
          <div className="mh-card-note" data-kind={steamOnly.note_source?.kind}>
            {steamOnly.note}
          </div>
        )}
      </section>
    );
  }
  if (!control) {
    return (
      <section className="mh-card">
        <div className="mh-card-note">{t.map.selectHint}</div>
      </section>
    );
  }
  const several = control.inputs.length > 1;
  return (
    <section className="mh-card" aria-live="polite">
      <div className="mh-card-head">
        <Glyph pad={pad} label={control.glyph} size={26} className="mh-card-glyph" />
        <span className="mh-card-name">{control.name}</span>
      </div>
      <div className="mh-card-body">
        {control.inputs.map((input) => (
          <InputDrives key={input.input} input={input} prefix={prefix} showInput={several} />
        ))}
      </div>
      {onChange && (
        <Focusable className="mh-card-actions" flow-children="row">
          <DialogButton className="mh-card-button" onClick={onChange}>
            {controlTargets(control).length ? t.map.changeButton : t.edit.giveJob}
          </DialogButton>
          {onDefault && (
            <DialogButton className="mh-card-button" onClick={onDefault}>
              {t.edit.backToDefault}
            </DialogButton>
          )}
        </Focusable>
      )}
    </section>
  );
}
