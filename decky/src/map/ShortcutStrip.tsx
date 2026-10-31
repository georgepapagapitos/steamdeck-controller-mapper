import { Fragment } from "react";
import type { Player } from "../data";
import { Glyph } from "../glyphs";
import { MAIN, heldButton } from "../panel/Shortcuts";
import { t } from "../strings";

// The emulator's main shortcuts on player 1's pad, one line above the button list: "Hold [View] and press
// [RB] Save state · [LB] Load state · …". A shortcut that doesn't start with the held button shows in full.
export function ShortcutStrip({ player }: { player: Player }) {
  const shortcuts = (player.hotkeys ?? []).filter((s) => MAIN.has(s.target));
  if (shortcuts.length === 0) return null;
  const held = heldButton(player.hotkeys ?? []);
  return (
    <div className="mh-strip-shortcuts" role="note" aria-label={t.shortcuts.title}>
      <span className="mh-strip-label">{t.shortcuts.title}</span>
      {held && (
        <span className="mh-strip-item">
          {t.shortcuts.hold}<Glyph pad={player.pad} label={held.glyph} size={22} className="mh-key" />{t.shortcuts.andPress}
        </span>
      )}
      {shortcuts.map((s) => {
        const keys = held && s.inputs.length > 1 && s.inputs[0].input === held.input ? s.inputs.slice(1) : s.inputs;
        return (
          <span key={s.target} className="mh-strip-item">
            {keys.map((k, n) => (
              <Fragment key={k.input}>
                {n > 0 && <span className="mh-keys-plus" aria-hidden="true">+</span>}
                <Glyph pad={player.pad} label={k.glyph} size={22} className="mh-key" />
              </Fragment>
            ))}
            <span>{s.label}</span>
          </span>
        );
      })}
    </div>
  );
}
