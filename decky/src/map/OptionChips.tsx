import type { Player } from "../data";
import { optionValue, sourceKindName } from "../format";
import { t } from "../strings";

// Per-player options (pak, deadzones) with where each came from, and the player number the game sees.
export function OptionChips({ player }: { player: Player }) {
  const options = player.options ?? [];
  const port = player.pad.emulator_port;
  if (!options.length && port == null) return null;
  return (
    <div className="mh-chips">
      {options.map((option) => {
        const value = optionValue(option);
        return (
          <div key={option.key} className="mh-chip">
            <span className={value ? "mh-chip-label" : "mh-chip-value"}>{option.label}</span>
            {value && <span className="mh-chip-value">{value}</span>}
            {option.source && (
              <span className="mh-badge" data-kind={option.source.kind}>
                {sourceKindName(option.source)}
              </span>
            )}
          </div>
        );
      })}
      {port != null && (
        <div className="mh-chip">
          <span className="mh-chip-label">{t.map.gameSees}</span>
          <span className="mh-chip-value">{t.playerLong(port)}</span>
        </div>
      )}
    </div>
  );
}

export function Legend() {
  return (
    <div className="mh-legend" aria-label={t.map.legend}>
      {(["rule", "emulator", "emudeck"] as const).map((kind) => (
        <span key={kind} className="mh-legend-item">
          <span className="mh-dot" data-kind={kind} aria-hidden="true" />
          {t.source[kind]}
        </span>
      ))}
      <span className="mh-legend-item">
        <span className="mh-dot" data-kind="none" aria-hidden="true" />
        {t.map.nothing}
      </span>
    </div>
  );
}
