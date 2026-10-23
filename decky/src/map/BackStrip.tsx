import type { PadInput } from "../data";
import { t } from "../strings";

export const steamKey = (input: PadInput) => `steam:${input.input}`;

// Inputs only Steam sees (`steam_only`): back buttons and paddles (Deck L4/L5/R4/R5, an 8BitDo's or Edge's
// paddles), a DualSense's touchpad click and mic button, a Switch pad's Capture. Emulators get Steam's virtual
// Xbox 360 pad, which has none of them. The list shows them under this heading.
export function steamOnlyTitle(inputs: PadInput[], isDeck: boolean): string {
  const backs = inputs.filter((i) => i.input.startsWith("paddle")).length;
  const backTitle = isDeck ? t.map.backButtons : t.map.backPaddles;
  return backs === inputs.length ? backTitle : backs === 0 ? t.map.extraButtons : t.map.backAndExtra;
}
