import { useQuickAccessVisible } from "@decky/api";
import { ButtonItem, Field, PanelSection, PanelSectionRow } from "@decky/ui";
import { useEffect, useRef } from "react";
import { FaCheck, FaChevronRight, FaExclamationTriangle } from "react-icons/fa";
import { useLastLaunch } from "../backend";
import type { LastLaunch, Player } from "../data";
import { gameTitle, launchLine, launchTime, modeName, optionText, outcomeText, policyText } from "../format";
import { openButtonMap } from "../navigation";
import { Loading, Message, SampleBanner, failureText } from "../States";
import { t } from "../strings";
import { Styles } from "../styles";

function NowPlaying({ data }: { data: LastLaunch }) {
  const { launch } = data;
  const good = launch.outcome === "changed" || launch.outcome === "no-changes";
  return (
    <PanelSection title={t.nowPlaying}>
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
    </PanelSection>
  );
}

function WhoIsPlayerOne({ data }: { data: LastLaunch }) {
  return (
    <PanelSection title={t.whoIsP1}>
      <PanelSectionRow>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <div className="mh-qam-text">{policyText(data.policy, data.launch.mode)}</div>
          {data.policy?.reason && <div className="mh-qam-text">{t.policyWhy(data.policy.reason)}</div>}
        </div>
      </PanelSectionRow>
    </PanelSection>
  );
}

function Footer({ data }: { data: LastLaunch }) {
  const { launch } = data;
  return (
    <PanelSection>
      <PanelSectionRow>
        <div className="mh-qam-facts">
          <div className="mh-qam-fact">
            <span>{t.lastLaunch}</span>
            <span>{launchTime(launch.ts)}</span>
          </div>
          {launch.ms != null && (
            <div className="mh-qam-fact">
              <span>{t.appliedLabel}</span>
              <span>{t.appliedIn(launch.ms)}</span>
            </div>
          )}
          <div className="mh-qam-fact">
            <span>{t.launchedFrom}</span>
            <span>{modeName(launch.mode)}</span>
          </div>
        </div>
      </PanelSectionRow>
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
      </PanelSection>
    );
  }

  return (
    <>
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
    </>
  );
}
