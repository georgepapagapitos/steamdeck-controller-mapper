import type { Player } from "../data";
import { shortPadName } from "../format";
import { Icon, padIcon } from "../glyphs";
import { t } from "../strings";

interface Props {
  players: Player[];
  current: number;
  onPick: (index: number) => void;
}

// One tab per player: the pad's icon and the player number, and on the current tab the pad's name too (four
// names don't fit beside the title at 854 px). L1/R1 switch them (handled by the route); a tap does too. They
// don't take focus: on a controller only the button list does.
export function PlayerTabs({ players, current, onPick }: Props) {
  if (players.length < 2) return null;
  return (
    <div className="mh-tabs" role="tablist" aria-label={t.map.playerTabs}>
      <span className="mh-bumper" aria-hidden="true">L1</span>
      {players.map((player, index) => {
        const on = index === current;
        return (
          <div
            key={player.player}
            className={`mh-tab${on ? " mh-tab-on" : ""}`}
            role="tab"
            aria-selected={on}
            aria-label={`${t.playerLong(player.player)}, ${player.pad.name}`}
            onClick={() => onPick(index)}
          >
            {padIcon(player.pad) && <Icon name={padIcon(player.pad)!} size={22} />}
            <span style={{ fontWeight: 700 }}>{t.playerShort(player.player)}</span>
            {on && <span>{shortPadName(player.pad.name)}</span>}
          </div>
        );
      })}
      <span className="mh-bumper" aria-hidden="true">R1</span>
    </div>
  );
}
