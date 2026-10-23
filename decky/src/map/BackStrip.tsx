import { Focusable } from "@decky/ui";
import type { PadInput } from "../data";
import { t } from "../strings";

interface Props {
  inputs: PadInput[];
  isDeck: boolean;
  selected: string | null;
  onSelect: (key: string) => void;
}

export const steamKey = (input: PadInput) => `steam:${input.input}`;

// Inputs only Steam sees (`steam_only`): back buttons and paddles (Deck L4/L5/R4/R5, an 8BitDo's or Edge's
// paddles), a DualSense's touchpad click and mic button, a Switch pad's Capture. Emulators get Steam's virtual
// Xbox 360 pad, which has none of them, so they're listed here instead of on the drawing.
export function BackStrip({ inputs, isDeck, selected, onSelect }: Props) {
  if (!inputs.length) return null;
  const backs = inputs.filter((i) => i.input.startsWith("paddle")).length;
  const backTitle = isDeck ? t.map.backButtons : t.map.backPaddles;
  const title = backs === inputs.length ? backTitle : backs === 0 ? t.map.extraButtons : t.map.backAndExtra;
  return (
    <Focusable className="mh-strip" flow-children="row" role="group" aria-label={title}>
      <span className="mh-strip-title">{title}</span>
      {inputs.map((input) => {
        const on = steamKey(input) === selected;
        return (
          <Focusable
            key={input.input}
            className={`mh-pill${on ? " mh-on" : ""}`}
            role="button"
            aria-pressed={on}
            aria-label={`${input.glyph}, ${input.name}: ${t.map.steamOnly}`}
            focusClassName="mh-focus"
            noFocusRing
            onActivate={() => onSelect(steamKey(input))}
            onClick={() => onSelect(steamKey(input))}
            onGamepadFocus={() => onSelect(steamKey(input))}
          >
            {input.glyph}
          </Focusable>
        );
      })}
      <span className="mh-strip-note">{isDeck ? t.map.steamOnlyNoteDeck : t.map.steamOnlyNote}</span>
    </Focusable>
  );
}
