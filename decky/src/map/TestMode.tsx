import { Focusable, type GamepadEvent } from "@decky/ui";
import { useEffect, useRef, useState } from "react";
import type { Pad } from "../data";
import { Glyph } from "../glyphs";
import { t } from "../strings";
import { listen, padIndices } from "./capture";

const HOLD_TO_LEAVE_MS = 900;

// Test mode: every press on the player's pad lights that button on both pictures (onInput), like a controller
// tester. One focused element swallows Steam's UI events so nothing navigates; holding B leaves, a tap of B is
// just B being tested.
export function TestMode({ pad, leaveGlyph, onInput, onLeave }: {
  pad: Pad;
  leaveGlyph: string; // the pad's own label for its east button (B, A on a Nintendo pad, ○)
  onInput: (input: string) => void;
  onLeave: () => void;
}) {
  const root = useRef<HTMLDivElement>(null);
  const [holding, setHolding] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  useEffect(() => {
    root.current?.focus();
    let timer: ReturnType<typeof setTimeout> | null = null;
    const handle = listen((input, pressed) => {
      if (input === "face_east") {
        if (pressed && !timer) {
          setHolding(true);
          timer = setTimeout(onLeave, HOLD_TO_LEAVE_MS);
        } else if (!pressed && timer) {
          clearTimeout(timer);
          timer = null;
          setHolding(false);
        }
      }
      if (pressed) onInput(input);
    }, { pads: padIndices(pad.vid_pid) });
    if (!handle) setUnavailable(true);
    return () => {
      if (timer) clearTimeout(timer);
      handle?.stop();
    };
  }, []);
  const swallow = (evt: GamepadEvent) => {
    evt.preventDefault?.();
    evt.stopPropagation?.();
  };
  return (
    <Focusable
      ref={root}
      className="mh-test"
      noFocusRing
      onButtonDown={swallow}
      onCancelButton={unavailable ? onLeave : swallow}
      onOKButton={swallow}
      onSecondaryButton={swallow}
      onOptionsButton={swallow}
      onMenuButton={swallow}
      onGamepadDirection={swallow}
      role="status"
      aria-live="polite"
    >
      <span className="mh-test-dot" aria-hidden="true" />
      <span className="mh-test-text">{unavailable ? t.test.unavailable : t.test.press(pad.name)}</span>
      <span className={`mh-test-leave${holding ? " mh-test-holding" : ""}`}>
        {t.test.hold}<Glyph pad={pad} label={leaveGlyph} size={22} className="mh-key" />{t.test.toStop}
        <span className="mh-test-bar" aria-hidden="true" />
      </span>
      <span className="mh-test-touch" role="button" onClick={onLeave}>{t.test.done}</span>
    </Focusable>
  );
}
