import { DialogButton } from "@decky/ui";
import type { PadInput } from "../data";
import { sourceWords } from "../format";
import { t } from "../strings";
import type { Control } from "./controls";

interface Props {
  prefix: string;
  control?: Control;
  steamOnly?: PadInput;
  isDeck: boolean;
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

// The selected control: its glyph and name, what each of its inputs drives, where that came from, and any note.
// "Change button" is shown so the layout is final, but editing isn't built yet.
export function DetailCard({ prefix, control, steamOnly, isDeck }: Props) {
  if (steamOnly) {
    return (
      <section className="mh-card" aria-live="polite">
        <div className="mh-card-head">
          <span className="mh-card-glyph">{steamOnly.glyph}</span>
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
        <span className="mh-card-glyph">{control.glyph}</span>
        <span className="mh-card-name">{control.name}</span>
      </div>
      {control.inputs.map((input) => (
        <InputDrives key={input.input} input={input} prefix={prefix} showInput={several} />
      ))}
      <div className="mh-card-actions">
        <DialogButton disabled focusable={false} style={{ width: "auto", minWidth: 0, minHeight: 44, padding: "0 16px" }}>
          {t.map.changeButton}
        </DialogButton>
        <span className="mh-soon">{t.map.comingSoon}</span>
      </div>
    </section>
  );
}
