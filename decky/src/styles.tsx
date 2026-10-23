// Colours from the approved mock-up (docs/08 Flow 3b): colour = where a mapping came from, orange = selected.
export const colors = {
  bg: "#0e141b",
  surface: "#1a2230",
  surfaceLow: "#151c26",
  border: "#33414f",
  divider: "#222c38",
  text: "#e6edf3",
  muted: "#9fb0c2",
  accent: "#1a9fff",
  onAccent: "#06121f",
  ok: "#7ee0a1",
  warn: "#ffcf8a",
  error: "#ff8a80",
  selected: "#ff9f43",
  rule: "#8fd0ff",
  emulator: "#c7d1db",
  emudeck: "#ffcf8a",
  none: "#5b6b7c",
};

const css = `
.mh-route {
  margin-top: 40px; height: calc(100% - 40px); box-sizing: border-box; overflow: hidden;
  background: ${colors.bg}; color: ${colors.text}; display: flex; flex-direction: column;
}
.mh-header {
  display: flex; align-items: center; gap: 16px; flex-wrap: nowrap;
  padding: 6px 16px; border-bottom: 1px solid ${colors.divider};
}
.mh-icon-button {
  width: 36px; height: 36px; flex: none; border-radius: 8px; background: ${colors.surface};
  display: flex; align-items: center; justify-content: center; color: ${colors.text};
}
.mh-header > div:nth-child(2) { flex: 1; }
.mh-title { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: 16px; font-weight: 700; line-height: 1.2; }
.mh-subtitle { font-size: 11px; color: ${colors.muted}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.mh-tabs { margin-left: auto; display: flex; gap: 8px; flex-wrap: nowrap; flex: none; }
.mh-tab {
  min-height: 34px; display: flex; align-items: center; gap: 6px; padding: 0 10px; border-radius: 8px;
  font-size: 12px; white-space: nowrap; background: ${colors.surface}; color: ${colors.text}; border: 1px solid ${colors.border};
  box-sizing: border-box;
}
.mh-tab-on { background: ${colors.accent}; color: ${colors.onAccent}; border-color: ${colors.accent}; }
.mh-body { flex: 1; display: flex; gap: 16px; padding: 10px 16px 46px; min-height: 0; }
.mh-left { flex: 0 0 300px; min-width: 0; min-height: 0; display: flex; flex-direction: column; gap: 8px; }
.mh-right { flex: 1; min-width: 0; min-height: 0; display: flex; flex-direction: column; gap: 8px; }

.mh-pad { position: relative; width: 100%; aspect-ratio: 640 / 400; container-type: inline-size; }
.mh-pad svg { position: absolute; inset: 0; width: 100%; height: 100%; }
.mh-spot {
  position: absolute; box-sizing: border-box; display: flex; align-items: center; justify-content: center;
  border: 2px solid ${colors.emulator}; background: ${colors.bg}; color: ${colors.text};
  font-weight: 700; line-height: 1; white-space: nowrap; overflow: visible;
}
.mh-spot::before { content: ""; position: absolute; inset: -6px; }
.mh-spot[data-kind="rule"] { border-color: ${colors.rule}; }
.mh-spot[data-kind="emudeck"] { border-color: ${colors.emudeck}; }
.mh-spot[data-kind="none"] { border-style: dashed; border-color: ${colors.none}; color: ${colors.muted}; }
.mh-spot.mh-on { border-color: ${colors.selected}; border-style: solid; background: #3a2a14; color: ${colors.text}; }
.mh-focus { outline: 3px solid #ffffff; outline-offset: 2px; }

.mh-strip {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 10px 12px;
  border-radius: 8px; border: 1px dashed ${colors.border};
}
.mh-strip-title { font-size: 13px; font-weight: 600; }
.mh-strip-note { font-size: 12px; color: ${colors.muted}; }
.mh-pill {
  min-height: 44px; min-width: 44px; box-sizing: border-box; padding: 0 12px; border-radius: 22px;
  display: flex; align-items: center; justify-content: center; background: ${colors.surfaceLow};
  border: 1px solid ${colors.border}; color: ${colors.muted}; font-size: 13px; font-weight: 600;
}
.mh-pill.mh-on { border-color: ${colors.selected}; color: ${colors.text}; background: #2a2015; }

.mh-chips { display: flex; gap: 6px; flex-wrap: wrap; }
.mh-chip {
  display: flex; align-items: center; gap: 6px; padding: 3px 8px; border-radius: 8px;
  background: ${colors.surface}; font-size: 11px; white-space: nowrap;
}
.mh-chip-label { color: ${colors.muted}; }
.mh-chip-value { font-weight: 600; }

.mh-badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 10px; font-weight: 600;
  line-height: 1.35; background: #2a3340; color: ${colors.emulator}; }
.mh-badge[data-kind="rule"] { background: #12385c; color: ${colors.rule}; }
.mh-badge[data-kind="emudeck"] { background: #3b2f1a; color: ${colors.emudeck}; }

.mh-legend { display: flex; gap: 10px; flex-wrap: nowrap; font-size: 10px; white-space: nowrap; color: ${colors.muted}; }
.mh-legend-item { display: flex; align-items: center; gap: 6px; }
.mh-dot { width: 10px; height: 10px; border-radius: 5px; flex: none; background: ${colors.emulator}; }
.mh-dot[data-kind="rule"] { background: ${colors.rule}; }
.mh-dot[data-kind="emudeck"] { background: ${colors.emudeck}; }
.mh-dot[data-kind="none"] { background: transparent; border: 1px dashed ${colors.none}; box-sizing: border-box; }

.mh-card {
  padding: 10px 12px; border-radius: 10px; background: ${colors.surface}; border: 1px solid ${colors.selected};
  display: flex; flex-direction: column; gap: 6px; flex: 1; min-height: 0; overflow: hidden;
}
.mh-card-head { display: flex; align-items: baseline; gap: 10px; }
.mh-card-glyph { font-size: 18px; font-weight: 700; }
.mh-card-name { font-size: 12px; color: ${colors.muted}; }
.mh-card-drive { display: flex; flex-direction: column; gap: 6px; }
.mh-card-target { font-size: 15px; font-weight: 600; }
.mh-card-input { font-size: 13px; color: ${colors.muted}; }
.mh-card-note { font-size: 11px; color: ${colors.muted}; line-height: 1.45; }
.mh-card-note[data-kind="rule"] { color: ${colors.rule}; }
.mh-card-note[data-kind="emudeck"] { color: ${colors.emudeck}; }
.mh-card-note[data-kind="emulator"] { color: ${colors.emulator}; }
.mh-card-note-source { opacity: 0.8; }
.mh-card-warn { font-size: 13px; color: ${colors.warn}; line-height: 1.45; }
.mh-card-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.mh-soon { font-size: 12px; color: ${colors.muted}; }

.mh-list-wrap { flex: 1; min-height: 0; overflow-y: auto; }
.mh-list { display: flex; flex-direction: column; gap: 3px; padding: 3px 4px 3px 2px; }
.mh-row {
  display: flex; align-items: center; gap: 10px; min-height: 34px; padding: 0 10px; border-radius: 8px;
  border: 1px solid transparent; background: ${colors.surfaceLow}; font-size: 13px; box-sizing: border-box;
  width: 100%;
}
.mh-row.mh-on { border-color: ${colors.selected}; background: #2a2015; }
.mh-row-glyph { width: 52px; flex: none; font-weight: 700; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mh-row-name { width: 96px; flex: none; font-size: 11px; color: ${colors.muted};
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mh-row-target { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mh-list-heading { display: flex; flex-direction: column; gap: 2px; margin: 8px 2px 2px; font-size: 10px;
  font-weight: 600; color: ${colors.muted}; text-transform: uppercase; letter-spacing: 0.8px; }
.mh-list-heading-note { text-transform: none; letter-spacing: 0; font-weight: 400; }
.mh-row-none { color: ${colors.muted}; }

.mh-state { display: flex; flex-direction: column; gap: 8px; padding: 4px 0; }
.mh-state-title { font-size: 15px; font-weight: 600; }
.mh-state-body { font-size: 13px; color: ${colors.muted}; line-height: 1.45; }
.mh-state-wrap { max-width: 560px; margin: 48px auto; padding: 0 32px; display: flex; flex-direction: column;
  gap: 16px; align-items: flex-start; }
.mh-sample {
  font-size: 12px; color: ${colors.onAccent}; background: ${colors.warn}; padding: 6px 10px; border-radius: 6px;
}
.mh-warnings { font-size: 12px; color: ${colors.warn}; display: flex; flex-direction: column; gap: 4px; }

.mh-sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.mh-qam-label {
  font-size: 12px; font-weight: 600; color: ${colors.muted}; text-transform: uppercase; letter-spacing: 0.8px;
}
.mh-qam-game { font-size: 16px; font-weight: 600; line-height: 1.3; }
.mh-qam-sub { font-size: 13px; color: ${colors.muted}; }
.mh-qam-outcome { display: flex; align-items: center; gap: 6px; font-size: 13px; margin-top: 2px; }
.mh-qam-outcome[data-outcome="changed"], .mh-qam-outcome[data-outcome="no-changes"] { color: ${colors.ok}; }
.mh-qam-outcome[data-outcome="skipped"] { color: ${colors.warn}; }
.mh-qam-outcome[data-outcome="error"] { color: ${colors.error}; }
.mh-qam-detail { font-size: 12px; color: ${colors.muted}; line-height: 1.4; }
.mh-player { display: flex; align-items: center; gap: 12px; min-width: 0; }
.mh-player-badge {
  width: 30px; height: 30px; flex: none; border-radius: 15px; background: #23415f; color: ${colors.rule};
  font-weight: 700; font-size: 14px; display: flex; align-items: center; justify-content: center;
}
.mh-player-text { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.mh-player-name { font-size: 14px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mh-player-detail { font-size: 12px; color: ${colors.muted}; }
.mh-qam-value { font-size: 13px; color: ${colors.text}; text-align: right; }
.mh-qam-text { font-size: 13px; color: ${colors.muted}; line-height: 1.45; }
.mh-qam-facts { display: flex; flex-direction: column; gap: 6px; font-size: 12px; color: ${colors.muted}; width: 100%; }
.mh-qam-fact { display: flex; justify-content: space-between; gap: 8px; }
.mh-qam-fact span:last-child { color: ${colors.text}; text-align: right; }
`;

// Rendered once by each screen; identical <style> blocks are harmless.
export function Styles() {
  return <style>{css}</style>;
}
