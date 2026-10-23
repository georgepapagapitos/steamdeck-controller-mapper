import { useQuickAccessVisible } from "@decky/api";
import { ButtonItem, Field, PanelSection, PanelSectionRow } from "@decky/ui";
import { useEffect, useRef } from "react";
import { FaCheck, FaChevronRight, FaExclamationTriangle } from "react-icons/fa";
import { useLastLaunch } from "../backend";
import type { LastLaunch, Player } from "../data";
import { gameTitle, launchLine, launchTime, modeName, optionText, outcomeText, policyText } from "../format";
import { openButtonMap, openRulesPage } from "../navigation";
import { Loading, Message, SampleBanner, failureText } from "../States";
import { t } from "../strings";
import { Styles } from "../styles";

// The last launch, game running or not: ES-DE stays open between games, so Steam can't say whether this one
// still runs. "Last played" is true either way.
function NowPlaying({ data }: { data: LastLaunch }) {
  const { launch } = data;
  const good = launch.outcome === "changed" || launch.outcome === "no-changes";
  return (
    <PanelSection title={t.lastPlayed(launchTime(launch.ts))}>
      <PanelSectionRow>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <div className="mh-qam-game">{gameTitle(launch)}</div>
          <div className="mh-qam-sub">{launchLine(launch)}</div>
          <div className="mh-qam-outcome" data-outcome={launch.outcome}>
            {good ? <FaCheck aria-hidden="true" size={12} /> : <FaExclamationTriangle aria-hidden="true" size={12} />}
            {outcomeText(launch)}
          </div>
          {launch.detail && <div className="mh-qam-detail">{launch.detail}</div>}
        </div>
      </PanelSectionRow>
    </PanelSection>
  );
}

function playerDetail(player: Player): string {
  return (player.options ?? []).filter((o) => o.key === "pak").map(optionText).join(" · ");
}

function PlayerRow({ player, index }: { player: Player; index: number }) {
  const detail = playerDetail(player);
  return (
    <Field
      focusable
      highlightOnFocus
      bottomSeparator="none"
      padding="compact"
      onActivate={() => openButtonMap(index)}
      onClick={() => openButtonMap(index)}
      onOKActionDescription={t.showButtonMap}
      label={
        <div className="mh-player" title={t.openPlayer(player.player, player.pad.name)}>
          <div className="mh-player-badge" aria-hidden="true">
            {player.player}
          </div>
          <div className="mh-player-text">
            <div className="mh-player-name">
              <span className="mh-sr-only">{`${t.playerLong(player.player)}: `}</span>
              {player.pad.name}
            </div>
            {detail && <div className="mh-player-detail">{detail}</div>}
          </div>
        </div>
      }
    >
      <FaChevronRight aria-hidden="true" size={14} />
    </Field>
  );
}

function Players({ data }: { data: LastLaunch }) {
  return (
    <PanelSection title={t.players}>
      {data.players.length === 0 ? (
        <PanelSectionRow>
          <div className="mh-qam-text">{t.noPlayers}</div>
        </PanelSectionRow>
      ) : (
        data.players.map((player, index) => (
          <PanelSectionRow key={player.player}>
            <PlayerRow player={player} index={index} />
          </PanelSectionRow>
        ))
      )}
      {data.players.length > 0 && (
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => openButtonMap(0)}>
            {t.showButtonMap}
          </ButtonItem>
        </PanelSectionRow>
      )}
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={openRulesPage}>
          {t.rules.open}
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
}

function WhoIsPlayerOne({ data }: { data: LastLaunch }) {
  // Field rows, not plain text: the QAM scrolls by moving focus, and text that can't take focus can't be reached.
  return (
    <PanelSection title={t.whoIsP1}>
      <PanelSectionRow>
        <Field focusable highlightOnFocus padding="compact" bottomSeparator="none"
          description={data.policy?.reason ? t.policyWhy(data.policy.reason) : undefined}>
          <div className="mh-qam-text">{policyText(data.policy, data.launch.mode)}</div>
        </Field>
      </PanelSectionRow>
    </PanelSection>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <PanelSectionRow>
      <Field focusable highlightOnFocus padding="compact" bottomSeparator="none" label={label}>
        <span className="mh-qam-value">{value}</span>
      </Field>
    </PanelSectionRow>
  );
}

function Footer({ data }: { data: LastLaunch }) {
  const { launch } = data;
  return (
    <PanelSection title={t.lastLaunch}>
      <Fact label={t.lastLaunch} value={launchTime(launch.ts)} />
      {launch.ms != null && <Fact label={t.appliedLabel} value={t.appliedIn(launch.ms)} />}
      <Fact label={t.launchedFrom} value={modeName(launch.mode)} />
    </PanelSection>
  );
}

// The Quick Access panel: what the running (or last) game got, who is which player, and the way into the map.
export function Panel() {
  const { state, reloading, reload } = useLastLaunch();
  const visible = useQuickAccessVisible();
  const wasVisible = useRef(visible);

  // Re-read whenever the panel is opened again: a new game may have launched since.
  useEffect(() => {
    if (visible && !wasVisible.current) reload();
    wasVisible.current = visible;
  }, [visible, reload]);

  if (state.status === "loading") {
    return (
      <PanelSection>
        <Styles />
        <PanelSectionRow>
          <Loading />
        </PanelSectionRow>
      </PanelSection>
    );
  }

  const { result } = state;
  if (!result.ok) {
    const { title, body, expected } = failureText(result);
    return (
      <PanelSection spinner={reloading}>
        <Styles />
        <div className="mh-qam">
        <PanelSectionRow>
          <SampleBanner result={result} />
        </PanelSectionRow>
        <PanelSectionRow>
          <Message title={title} body={body} />
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={reload} disabled={reloading}>
            {expected ? t.refresh : t.retry}
          </ButtonItem>
        </PanelSectionRow>
        {result.code === "no-launch" && (
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={openRulesPage}>
              {t.rules.open}
            </ButtonItem>
          </PanelSectionRow>
        )}
        </div>
      </PanelSection>
    );
  }

  return (
    <div className="mh-qam">
      <Styles />
      {result.sample && (
        <PanelSection>
          <PanelSectionRow>
            <SampleBanner result={result} />
          </PanelSectionRow>
        </PanelSection>
      )}
      <NowPlaying data={result.data} />
      <Players data={result.data} />
      <WhoIsPlayerOne data={result.data} />
      <Footer data={result.data} />
    </div>
  );
}
