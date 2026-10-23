import { toaster } from "@decky/api";
import { ConfirmModal, DialogButton, Focusable, Menu, MenuItem, ModalRoot, Navigation, showContextMenu,
  showModal } from "@decky/ui";
import { useState } from "react";
import type { Launch, Player } from "../data";
import { shortGameTitle } from "../format";
import { RULES_ROUTE } from "../navigation";
import { type EditResult, type Op, editRules, resetRules, setRulesOn } from "../rules";
import { t } from "../strings";
import { Styles } from "../styles";
import { type Control, controlDrives } from "./controls";
import { EditFlow, ResultView, undoEdit } from "./EditFlow";

export interface MapContext {
  launch: Launch;
  player: Player;
  players: Player[];
  prefix: string;
  onSaved: (delta: number) => void; // +1 per saved edit, -1 per undo: the map's "applies next launch" banner
}

const named = (prefix: string, label: string) => (prefix ? `${prefix} ${label}` : label);

export function openEdit(ctx: MapContext, control: Control) {
  showModal(<EditFlow launch={ctx.launch} player={ctx.player} players={ctx.players} control={control}
    prefix={ctx.prefix} onSaved={ctx.onSaved} />);
}

// The control's console inputs that one of the user's rules puts there: what "Back to default" takes out.
export function ruleDrives(control: Control) {
  const seen = new Set<string>();
  return controlDrives(control).filter((d) => {
    if (d.source?.kind !== "rule" || !d.source.rule_id || seen.has(d.target)) return false;
    seen.add(d.target);
    return true;
  });
}

function Result({ closeModal, result, players, onSaved }: {
  closeModal?: () => void;
  result: EditResult;
  players: Player[];
  onSaved: (delta: number) => void;
}) {
  const close = () => closeModal?.();
  return (
    <ModalRoot onCancel={close} closeModal={close}>
      <Styles />
      <div className="mh-modal">
        <ResultView result={result} players={players} onDone={close}
          onUndo={() => undoEdit(result, onSaved).then(close)} />
      </div>
    </ModalRoot>
  );
}

export function backToDefault(ctx: MapContext, control: Control) {
  const drives = ruleDrives(control);
  if (!drives.length) return;
  const what = drives.map((d) => named(ctx.prefix, d.label)).join(", ");
  const rule = [...new Set(drives.map((d) => d.source.rule_label || d.source.rule_id))].join(", ");
  const ops: Op[] = drives.map((d) => ({ op: "unset", target: d.target, rule: d.source.rule_id! }));
  const modal = showModal(
    <ConfirmModal
      strTitle={t.edit.defaultTitle}
      strDescription={t.edit.defaultBody(what, control.glyph, rule ?? "")}
      strOKButtonText={t.edit.backToDefault}
      strCancelButtonText={t.edit.cancel}
      onOK={async () => {
        const answer = await editRules(ops);
        modal.Close();
        if (!answer.ok) {
          toaster.toast({ title: t.edit.failed, body: answer.error, critical: true });
          return;
        }
        ctx.onSaved(1);
        showModal(<Result result={answer.data} players={ctx.players} onSaved={ctx.onSaved} />);
      }}
    />,
  );
}

function ResetDone({ closeModal, ids, labels, onSaved }: {
  closeModal?: () => void;
  ids: string[];
  labels: string[];
  onSaved: (delta: number) => void;
}) {
  const [busy, setBusy] = useState(false);
  const close = () => closeModal?.();
  const undo = async () => {
    setBusy(true);
    const answer = await setRulesOn(ids, true);
    if (answer.ok) {
      onSaved(-1);
      toaster.toast({ title: t.title, body: t.edit.undone });
    } else {
      toaster.toast({ title: t.edit.failed, body: answer.error, critical: true });
    }
    close();
  };
  // B closes; only the Undo button undoes.
  return (
    <ModalRoot onCancel={close} closeModal={close}>
      <Styles />
      <div className="mh-modal">
        <div className="mh-modal-title">{t.edit.resetDone(ids.length)}</div>
        <ul className="mh-rule-names">{labels.map((l, i) => <li key={i}>{l}</li>)}</ul>
        <div className="mh-modal-note">{t.edit.savedBody}</div>
        <Focusable className="mh-modal-buttons" flow-children="row">
          <DialogButton className="mh-modal-button" onClick={close}>{t.edit.done}</DialogButton>
          <DialogButton className="mh-modal-button" disabled={busy} onClick={undo}>{t.edit.undo}</DialogButton>
        </Focusable>
      </div>
    </ModalRoot>
  );
}

// Turn off the rules for this game, or for every game of the system: a dry run says which first.
async function reset(ctx: MapContext, game: string | null) {
  const { system } = ctx.launch;
  const dry = await resetRules(system, game, true);
  if (!dry.ok) {
    toaster.toast({ title: t.edit.failed, body: dry.error, critical: true });
    return;
  }
  if (!dry.data.rules.length) {
    toaster.toast({ title: t.title, body: t.edit.resetNothing });
    return;
  }
  const modal = showModal(
    <ConfirmModal
      strTitle={t.edit.resetTitle}
      strDescription={
        <>
          <Styles />
          <ul className="mh-rule-names">{dry.data.labels.map((l, i) => <li key={i}>{l}</li>)}</ul>
          <div className="mh-modal-note">{t.edit.resetBody}</div>
        </>
      }
      strOKButtonText={t.edit.resetOk}
      strCancelButtonText={t.edit.cancel}
      bDestructiveWarning
      onOK={async () => {
        const answer = await resetRules(system, game, false);
        modal.Close();
        if (!answer.ok) {
          toaster.toast({ title: t.edit.failed, body: answer.error, critical: true });
          return;
        }
        ctx.onSaved(1);
        showModal(<ResetDone ids={answer.data.rules} labels={answer.data.labels} onSaved={ctx.onSaved} />);
      }}
    />,
  );
}

export function openRules() {
  Navigation.Navigate(RULES_ROUTE);
}

// The map's Options menu (the ≡ button, or the ⋯ button in the header).
export function openMenu(ctx: MapContext, anchor?: EventTarget) {
  const system = ctx.launch.system_name || ctx.launch.system.toUpperCase();
  showContextMenu(
    <Menu label={t.edit.menu} cancelText={t.edit.cancel}>
      <MenuItem onSelected={openRules}>{t.edit.openRules}</MenuItem>
      {ctx.launch.game && (
        <MenuItem onSelected={() => reset(ctx, ctx.launch.game ?? null)}>
          {t.edit.resetGame(shortGameTitle(ctx.launch))}
        </MenuItem>
      )}
      <MenuItem tone="destructive" onSelected={() => reset(ctx, null)}>{t.edit.resetSystem(system)}</MenuItem>
    </Menu>,
    anchor,
  );
}
