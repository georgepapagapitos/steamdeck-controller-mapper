import { DialogButton, Focusable, GamepadButton, type GamepadEvent, Navigation } from "@decky/ui";
import { type ReactNode, useMemo, useState } from "react";
import { FaChevronLeft } from "react-icons/fa";
import { useLastLaunch } from "../backend";
import type { LastLaunch } from "../data";
import { launchLine, programName, shortGameTitle, systemPrefix, warningText } from "../format";
import { takeRequestedPlayer } from "../navigation";
import { Loading, Message, SampleBanner, failureText } from "../States";
import { t } from "../strings";
import { Styles } from "../styles";
import { steamKey } from "./BackStrip";
import { ControlList } from "./ControlList";
import { groupControls, steamOnlyInputs } from "./controls";
import { DetailCard } from "./DetailCard";
import { Legend, OptionChips } from "./OptionChips";
import { PadDrawing } from "./PadDrawing";
import { PlayerTabs } from "./PlayerTabs";

const goBack = () => Navigation.NavigateBack();

function BackButton() {
  return (
    <Focusable
      className="mh-icon-button"
      role="button"
      aria-label={t.map.back}
      focusClassName="mh-focus"
      noFocusRing
      onActivate={goBack}
      onClick={goBack}
    >
      <FaChevronLeft aria-hidden="true" />
    </Focusable>
  );
}

function Header({ title, subtitle, children }: { title: string; subtitle?: string; children?: ReactNode }) {
  return (
    <div className="mh-header">
      <BackButton />
      <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
        <div className="mh-title">{title}</div>
        {subtitle && <div className="mh-subtitle">{subtitle}</div>}
      </div>
      {children}
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

  // L1/R1 switch players, like tabs elsewhere in Steam.
  const onButtonDown = (evt: GamepadEvent) => {
    const button = evt.detail.button;
    if (button === GamepadButton.BUMPER_LEFT && current > 0) pick(current - 1);
    if (button === GamepadButton.BUMPER_RIGHT && current < players.length - 1) pick(current + 1);
  };

  const launch = data.launch;
  const prefix = systemPrefix(launch);
  const subtitle = [launch.system_name || launch.system.toUpperCase(), programName(launch.core || launch.emulator), t.map.asApplied]
    .filter(Boolean)
    .join(" · ");
  const isDeck = player?.pad.shape === "deck";
  const control = controls.find((c) => c.key === selected);
  const steamOnly = backs.find((b) => steamKey(b) === selected);
  const warnings = data.warnings ?? [];

  return (
    <Focusable
      className="mh-route"
      onButtonDown={onButtonDown}
      onCancelButton={goBack}
      onCancelActionDescription={t.map.goBack}
    >
      <Header title={shortGameTitle(launch)} subtitle={subtitle}>
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
              <PadDrawing padName={player.pad.name} shape={player.pad.shape} controls={controls} selected={selected} />
            ) : (
              <Message title={player.pad.name} body={t.map.noInputs} />
            )}
            <Legend />
            <DetailCard prefix={prefix} control={control} steamOnly={steamOnly} isDeck={isDeck} />
          </div>
          <div className="mh-right">
            <OptionChips player={player} />
            {warnings.length > 0 && (
              <div className="mh-warnings" role="note" aria-label={t.map.warnings}>
                {warnings.map((w, i) => (
                  <div key={i}>{warningText(w)}</div>
                ))}
              </div>
            )}
            <ControlList controls={controls} steamOnly={backs} isDeck={isDeck} selected={selected} prefix={prefix}
              onSelect={setSelected} />
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
