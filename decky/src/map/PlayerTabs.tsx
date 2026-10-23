import { Focusable } from "@decky/ui";
import type { Player } from "../data";
import { shortPadName } from "../format";
import { t } from "../strings";

interface Props {
  players: Player[];
  current: number;
  onPick: (index: number) => void;
}

// One tab per player. L1/R1 also switch tabs (handled by the route).
export function PlayerTabs({ players, current, onPick }: Props) {
  if (players.length < 2) return null;
  return (
    <Focusable className="mh-tabs" flow-children="row" role="tablist" aria-label={t.map.playerTabs}>
      {players.map((player, index) => {
        const on = index === current;
        return (
          <Focusable
            key={player.player}
            className={`mh-tab${on ? " mh-tab-on" : ""}`}
            role="tab"
            aria-selected={on}
            aria-label={`${t.playerLong(player.player)}, ${player.pad.name}`}
            focusClassName="mh-focus"
            noFocusRing
            onActivate={() => onPick(index)}
            onClick={() => onPick(index)}
          >
            <span style={{ fontWeight: 700 }}>{t.playerShort(player.player)}</span>
            <span>{shortPadName(player.pad.name)}</span>
          </Focusable>
        );
      })}
    </Focusable>
  );
}
