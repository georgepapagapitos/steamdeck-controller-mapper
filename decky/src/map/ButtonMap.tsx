import { DialogButton, Focusable, GamepadButton, type GamepadEvent, Navigation } from "@decky/ui";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { FaBars, FaChevronLeft } from "react-icons/fa";
import { useLastLaunch } from "../backend";
import type { LastLaunch } from "../data";
import { launchLine, launchTime, programName, shortGameTitle, systemPrefix, warningText } from "../format";
import { takeRequestedPlayer } from "../navigation";
import { getSystemLogo, notePending, pendingFor } from "../rules";
import { undoLast, useUndo } from "../undo";
import { Loading, Message, SampleBanner, failureText } from "../States";
import { t } from "../strings";
import { Styles } from "../styles";
import { steamKey } from "./BackStrip";
import { ControlList } from "./ControlList";
import { type Control, groupControls, steamOnlyInputs } from "./controls";
import { type MapContext, backToDefault, openEdit, openMenu, ruleDrives } from "./actions";
import { DetailCard } from "./DetailCard";
import { Legend, OptionChips } from "./OptionChips";
import { PadDrawing } from "./PadDrawing";
import { PlayerTabs } from "./PlayerTabs";

const goBack = () => Navigation.NavigateBack();

// The header's back and ≡ buttons are for touch: on a controller, B goes back and ≡ opens the menu (Steam's footer
// says so), and only the button list takes focus, so the D-pad just moves up and down it.
function TouchButton({ label, onClick, children }: { label: string; onClick: () => void; children: ReactNode }) {
  return (
    <div className="mh-icon-button" role="button" aria-label={label} onClick={onClick}>
      {children}
    </div>
  );
}

// The system's logo from the user's active ES-DE theme (never shipped with the plugin); null when the theme has
// none for it, and then the header names the system in words.
function useSystemLogo(system: string | undefined): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    setUrl(null);
    if (system) getSystemLogo(system).then((answer) => answer.ok && setUrl(answer.data.url));
  }, [system]);
  return url;
}

function Header({ title, subtitle, logo, children, onMenu }: {
  title: string;
  subtitle?: string;
  logo?: string | null;
  children?: ReactNode;
  onMenu?: () => void;
}) {
  return (
    <div className="mh-header">
      <TouchButton label={t.map.back} onClick={goBack}><FaChevronLeft aria-hidden="true" /></TouchButton>
      {logo && <img className="mh-logo" src={logo} alt="" />}
      <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
        <div className="mh-title">{title}</div>
        {subtitle && <div className="mh-subtitle">{subtitle}</div>}
      </div>
      {children}
      {onMenu && <TouchButton label={t.edit.menu} onClick={onMenu}><FaBars aria-hidden="true" /></TouchButton>}
    </div>
  );
}

function MapView({ data, sample }: { data: LastLaunch; sample: boolean }) {
  const players = data.players;
  const [current, setCurrent] = useState(() => Math.min(takeRequestedPlayer(), Math.max(players.length - 1, 0)));
  const player = players[current];
  const controls = useMemo(() => groupControls(player?.inputs ?? []), [player]);
  const backs = useMemo(() => steamOnlyInputs(player?.inputs ?? []), [player]);
  const [selected, setSelected] = useState<string | null>(() => controls[0]?.key ?? null);

  const pick = (index: number) => {
    if (index === current || !players[index]) return;
    setCurrent(index);
    setSelected(groupControls(players[index].inputs)[0]?.key ?? null);
  };

  // Development aid, temporary (remove before pushing): focus moves within this page and the buttons that reached
  // it, in window.mhFocusLog (Steam's debugger, SharedJSContext). Watches only this page's own elements, so the
  // text it notes is our own labels, never Steam's UI.
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const page = root.current;
    const doc = page?.ownerDocument;
    if (!page || !doc) return;
    const log = ((window as unknown as Record<string, unknown>).mhFocusLog ??= []) as unknown[];
    const note = (what: string) => log.length < 400 && log.push(`${Date.now() % 100000} ${what}`);
    const describe = (el: Element) => `${el.className.toString().split(" ").filter((c) => c.startsWith("mh-") || c === "DialogButton")
      .join(".")}|${(el.textContent ?? "").trim().slice(0, 24)}`;
    const focused = page.querySelector(".gpfocus");
    note(`open ${focused ? describe(focused) : "(no focus on this page)"}`);
    const observer = new MutationObserver((records) => {
      for (const r of records) {
        const el = r.target as Element;
        if (el.classList?.contains("gpfocus") && !(r.oldValue ?? "").includes("gpfocus")) note(`focus ${describe(el)}`);
      }
    });
    observer.observe(page, { subtree: true, attributes: true, attributeFilter: ["class"], attributeOldValue: true });
    return () => observer.disconnect();
  }, []);

  // L1/R1 switch players, like tabs elsewhere in Steam.
  const onButtonDown = (evt: GamepadEvent) => {
    const log = (window as unknown as Record<string, unknown[]>).mhFocusLog;
    if (log && log.length < 400) log.push(`${Date.now() % 100000} button ${evt.detail.button}`);
    const button = evt.detail.button;
    if (button === GamepadButton.BUMPER_LEFT && current > 0) pick(current - 1);
    if (button === GamepadButton.BUMPER_RIGHT && current < players.length - 1) pick(current + 1);
  };

  const launch = data.launch;
  const prefix = systemPrefix(launch);
  const logo = useSystemLogo(launch.system);
  // The map is the last launch's, game running or not: say so ("Last played today, 14:03"), or it reads as if
  // that game were running.
  const subtitle = [t.map.lastPlayed(launchTime(launch.ts)), logo ? "" : launch.system_name || launch.system.toUpperCase(),
    programName(launch.core || launch.emulator)]
    .filter(Boolean)
    .join(" · ");
  const isDeck = player?.pad.shape === "deck";
  const control = controls.find((c) => c.key === selected);
  const steamOnly = backs.find((b) => steamKey(b) === selected);
  const warnings = data.warnings ?? [];
  const [pending, setPending] = useState(() => pendingFor(launch.ts));
  const right = useRef<HTMLDivElement>(null);
  const ctx: MapContext | null = player ? {
    launch, player, players, prefix,
    refocus: () => setTimeout(() => right.current?.querySelector<HTMLElement>(".mh-row.mh-on")?.focus(), 80),
    onSaved: (delta: number) => {
      notePending(launch.ts, delta);
      setPending(pendingFor(launch.ts));
    },
  } : null;
  const canDefault = (c: Control) => ruleDrives(c).length > 0;
  const undo = useUndo();
  const menu = ctx ? () => openMenu(ctx, undo?.label ?? null) : undefined;

  return (
    <Focusable
      ref={root}
      className="mh-route"
      onButtonDown={onButtonDown}
      onCancelButton={goBack}
      onCancelActionDescription={t.map.goBack}
      onMenuButton={menu}
      onMenuActionDescription={menu ? t.edit.menu : undefined}
      onOptionsButton={undo ? () => undoLast() : undefined}
      onOptionsActionDescription={undo ? t.edit.undo : undefined}
    >
      <Header title={shortGameTitle(launch)} subtitle={subtitle} logo={logo} onMenu={menu}>
        <PlayerTabs players={players} current={current} onPick={pick} />
      </Header>
      {!player ? (
        <div className="mh-state-wrap">
          <Message title={launchLine(launch)} body={t.map.noPlayers} />
        </div>
      ) : (
        <div className="mh-body">
          <div className="mh-left">
            {sample && <SampleBanner result={{ ok: true, data, sample }} />}
            {controls.length ? (
              <PadDrawing pad={player.pad} controls={controls} selected={selected} />
            ) : (
              <Message title={player.pad.name} body={t.map.noInputs} />
            )}
            <Legend />
            <DetailCard pad={player.pad} prefix={prefix} control={control} steamOnly={steamOnly} isDeck={isDeck} />
          </div>
          <div className="mh-right" ref={right}>
            {pending > 0 && <div className="mh-pending" role="status">{t.edit.pending(pending)}</div>}
            <OptionChips player={player} />
            {warnings.length > 0 && (
              <div className="mh-warnings" role="note" aria-label={t.map.warnings}>
                {warnings.map((w, i) => (
                  <div key={i}>{warningText(w)}</div>
                ))}
              </div>
            )}
            <ControlList pad={player.pad} controls={controls} steamOnly={backs} isDeck={isDeck} selected={selected}
              prefix={prefix} onSelect={setSelected} onChange={ctx ? (c) => openEdit(ctx, c) : undefined}
              onDefault={ctx ? (c) => backToDefault(ctx, c) : undefined} canDefault={canDefault} />
          </div>
        </div>
      )}
    </Focusable>
  );
}

// Full-screen route: what each button of each player's pad does in the game launched last.
export function ButtonMap() {
  const { state, reload } = useLastLaunch();
  let body: ReactNode;
  if (state.status === "loading") {
    body = (
      <Focusable className="mh-route" onCancelButton={goBack}>
        <Header title={t.showButtonMap} />
        <div className="mh-state-wrap">
          <Loading />
        </div>
      </Focusable>
    );
  } else if (state.result.ok) {
    body = <MapView data={state.result.data} sample={!!state.result.sample} />;
  } else {
    const { title, body: text, expected } = failureText(state.result);
    body = (
      <Focusable className="mh-route" onCancelButton={goBack}>
        <Header title={t.showButtonMap} />
        <div className="mh-state-wrap">
          <SampleBanner result={state.result} />
          <Message title={title} body={text} />
          {!expected && (
            <DialogButton style={{ width: "auto", minHeight: 44 }} onClick={reload}>
              {t.retry}
            </DialogButton>
          )}
        </div>
      </Focusable>
    );
  }
  return (
    <>
      <Styles />
      {body}
    </>
  );
}
