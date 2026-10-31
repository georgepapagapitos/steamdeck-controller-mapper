import { Field, PanelSection, PanelSectionRow } from "@decky/ui";
import { Fragment, type ReactNode, useState } from "react";
import type { LastLaunch, Pad, Shortcut } from "../data";
import { Glyph } from "../glyphs";
import { t } from "../strings";

// The ones a player looks for first; the rest (pause, save slots, screenshot, fullscreen) sit behind "more".
export const MAIN = new Set([
  "hotkey.save_state", "hotkey.load_state", "hotkey.fast_forward", "hotkey.fast_forward_hold", "hotkey.rewind",
  "hotkey.menu", "hotkey.exit",
]);

// The button most shortcuts start with (EmuDeck's Select), when at least two share it: the section says "Hold − and
// press" once, and each row shows only what to press with it.
export function heldButton(shortcuts: Shortcut[]): Shortcut["inputs"][number] | null {
  const counts = new Map<string, number>();
  for (const s of shortcuts) if (s.inputs.length > 1) counts.set(s.inputs[0].input, (counts.get(s.inputs[0].input) ?? 0) + 1);
  let best: string | null = null;
  for (const [input, n] of counts) if (n >= 2 && (best === null || n > counts.get(best)!)) best = input;
  return best ? shortcuts.find((s) => s.inputs[0].input === best)!.inputs[0] : null;
}

function Keys({ pad, inputs }: { pad: Pad; inputs: Shortcut["inputs"] }) {
  return (
    <span className="mh-keys" aria-label={inputs.map((i) => i.glyph).join(" + ")}>
      {inputs.map((i, n) => (
        <Fragment key={i.input}>
          {n > 0 && <span className="mh-keys-plus" aria-hidden="true">+</span>}
          <Glyph pad={pad} label={i.glyph} size={28} className="mh-key" />
        </Fragment>
      ))}
    </span>
  );
}

// Field rows, not plain text: the QAM scrolls by moving focus, and text that can't take focus can't be reached.
function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <PanelSectionRow>
      <Field className="mh-qam-field" focusable highlightOnFocus padding="compact" bottomSeparator="none" label={label}>
        {children}
      </Field>
    </PanelSectionRow>
  );
}

// The emulator's shortcuts on player 1's pad: save, load, fast forward, quit, as the pad's own buttons.
export function Shortcuts({ data }: { data: LastLaunch }) {
  const [all, setAll] = useState(false);
  const player = data.players.find((p) => p.hotkeys?.length);
  if (!player) return null;
  const shortcuts = player.hotkeys!;
  const held = heldButton(shortcuts);
  const main = shortcuts.filter((s) => MAIN.has(s.target));
  const rest = shortcuts.filter((s) => !MAIN.has(s.target));
  const shown = all || main.length === 0 ? shortcuts : main;
  const pad = player.pad;
  return (
    <PanelSection title={t.shortcuts.title}>
      {held && (
        <PanelSectionRow>
          <div className="mh-hold">
            {t.shortcuts.hold}
            <Glyph pad={pad} label={held.glyph} size={28} className="mh-key" />
            {t.shortcuts.andPress}
            {data.players.length > 1 && <span className="mh-hold-pad">{t.shortcuts.onPad(pad.name)}</span>}
          </div>
        </PanelSectionRow>
      )}
      {shown.map((s) => (
        <Row key={s.target} label={s.label}>
          <Keys pad={pad} inputs={held && s.inputs.length > 1 && s.inputs[0].input === held.input ? s.inputs.slice(1) : s.inputs} />
        </Row>
      ))}
      {!shortcuts.some((s) => s.target === "hotkey.exit") && (
        // xemu: nothing on the pad quits, and its View + Menu (quit everywhere else) opens the menu instead.
        <Row label={t.shortcuts.quit}><span className="mh-note">{t.shortcuts.quitInMenu}</span></Row>
      )}
      {main.length > 0 && rest.length > 0 && (
        <PanelSectionRow>
          <Field className="mh-qam-field" focusable highlightOnFocus padding="compact" bottomSeparator="none"
            onActivate={() => setAll(!all)} onClick={() => setAll(!all)}
            label={<span className="mh-qam-more">{all ? t.shortcuts.fewer : t.shortcuts.more(rest.length)}</span>} />
        </PanelSectionRow>
      )}
    </PanelSection>
  );
}

// What isn't obvious from the buttons alone, on player 1's pad: a button that does nothing by itself but changes the
// others (Mupen64Plus-Next's ZR for C buttons). The hotkey button is left out: Shortcuts says it.
export function GoodToKnow({ data }: { data: LastLaunch }) {
  const player = data.players[0];
  if (!player) return null;
  const held = heldButton(data.players.find((p) => p.hotkeys?.length)?.hotkeys ?? []);
  const notes = player.inputs.filter((i) => i.note_short && i.drives.length === 0 && !i.held_with && !i.steam_only && i.input !== held?.input);
  if (notes.length === 0) return null;
  return (
    <>
      {notes.map((i) => (
        <PanelSectionRow key={i.input}>
          <Field className="mh-qam-field" focusable highlightOnFocus padding="compact" bottomSeparator="none"
            label={<span className="mh-note"><Glyph pad={player.pad} label={i.glyph} size={28} className="mh-key" />{i.note_short}</span>} />
        </PanelSectionRow>
      ))}
    </>
  );
}
