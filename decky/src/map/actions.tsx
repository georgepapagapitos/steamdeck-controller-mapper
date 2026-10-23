import { toaster } from "@decky/api";
import { ConfirmModal, Menu, MenuItem, Navigation, showContextMenu, showModal } from "@decky/ui";
import type { Launch, Player } from "../data";
import { shortGameTitle, shortPadName } from "../format";
import { RULES_ROUTE } from "../navigation";
import { type EditResult, type Op, editRules, resetRules, setRulesOn } from "../rules";
import { t } from "../strings";
import { Styles } from "../styles";
import { setUndo, undoLast } from "../undo";
import { type Control, controlDrives } from "./controls";
import { EditFlow, type Where } from "./EditFlow";

export interface MapContext {
  launch: Launch;
  player: Player;
  players: Player[];
  prefix: string;
  onSaved: (delta: number) => void; // +1 per saved change, -1 per undo: the map's "applies next launch" note
  refocus: () => void; // after a modal: focus back on the row you were on
}

const named = (prefix: string, label: string) => (prefix ? `${prefix} ${label}` : label);

// After a change: a toast saying where it applies and how to undo it, and Y (or the ≡ menu) as the undo.
function saved(ctx: MapContext, result: EditResult, label: string, body: string) {
  ctx.onSaved(1);
  setUndo({
    label,
    run: async () => {
      const answer = await editRules(result.undo);
      if (!answer.ok) return answer.error;
      ctx.onSaved(-1);
      return null;
    },
  });
  toaster.toast({ title: t.edit.saved, body });
}

function whereWords(ctx: MapContext, where: Where): string {
  const system = ctx.launch.system_name || ctx.launch.system.toUpperCase();
  return where === "game" ? shortGameTitle(ctx.launch)
    : where === "system" ? t.edit.whereSystem(system)
    : t.edit.wherePad(shortPadName(ctx.player.pad.name), system);
}

export function openEdit(ctx: MapContext, control: Control) {
  showModal(
    <EditFlow launch={ctx.launch} player={ctx.player} players={ctx.players} control={control} prefix={ctx.prefix}
      onClosed={ctx.refocus} onSaved={(result, where, what) => {
        const words = whereWords(ctx, where);
        saved(ctx, result, `${what} · ${words}`, t.edit.savedBody(words));
      }} />,
  );
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

// Takes the rule's binding out at once (it's one press to undo), and says what the button does now.
export async function backToDefault(ctx: MapContext, control: Control) {
  const drives = ruleDrives(control);
  if (!drives.length) return;
  const what = drives.map((d) => named(ctx.prefix, d.label)).join(", ");
  const ops: Op[] = drives.map((d) => ({ op: "unset", target: d.target, rule: d.source.rule_id! }));
  const answer = await editRules(ops);
  if (!answer.ok) {
    toaster.toast({ title: t.edit.failed, body: answer.error, critical: true });
    return;
  }
  ctx.onSaved(1);
  setUndo({
    label: t.edit.defaultUndo(what),
    run: async () => {
      const back = await editRules(answer.data.undo);
      if (!back.ok) return back.error;
      ctx.onSaved(-1);
      return null;
    },
  });
  toaster.toast({ title: t.edit.defaultDone(what), body: t.edit.undoHint });
}

// Back to the emulator's defaults: turn off your rules for this game, or for every game of the system, in one
// modal. Dry runs list the rules first; the system's button shows only when it turns off more than the game's
// (the system's reset includes its game rules). Nothing is deleted, and Y undoes it.
export async function backToDefaults(ctx: MapContext) {
  const { system, game } = ctx.launch;
  const systemName = ctx.launch.system_name || system.toUpperCase();
  const [forGame, forSystem] = await Promise.all([game ? resetRules(system, game, true) : null, resetRules(system, null, true)]);
  if (!forSystem.ok || (forGame && !forGame.ok)) {
    const error = !forSystem.ok ? forSystem.error : forGame && !forGame.ok ? forGame.error : "";
    toaster.toast({ title: t.edit.failed, body: error, critical: true });
    return;
  }
  const gameRules = forGame?.ok ? forGame.data : null;
  const all = forSystem.data;
  if (!all.rules.length) {
    toaster.toast({ title: t.edit.resetNothingTitle, body: t.edit.resetNothing });
    ctx.refocus();
    return;
  }
  const gameOnly = !!gameRules?.rules.length;
  const more = all.rules.length > (gameRules?.rules.length ?? 0);
  const run = async (scope: string | null) => {
    modal.Close();
    ctx.refocus();
    const answer = await resetRules(system, scope, false);
    if (!answer.ok) {
      toaster.toast({ title: t.edit.failed, body: answer.error, critical: true });
      return;
    }
    const ids = answer.data.rules;
    ctx.onSaved(1);
    setUndo({
      label: t.edit.resetDone(ids.length),
      run: async () => {
        const back = await setRulesOn(ids, true);
        if (!back.ok) return back.error;
        ctx.onSaved(-1);
        return null;
      },
    });
    toaster.toast({ title: t.edit.resetDone(ids.length), body: t.edit.undoHint });
  };
  const listed = gameOnly ? gameRules!.labels : all.labels;
  const modal = showModal(
    <ConfirmModal
      strTitle={t.edit.defaultsTitle}
      strDescription={
        <>
          <Styles />
          <div className="mh-modal-note">{gameOnly ? t.edit.defaultsGame(shortGameTitle(ctx.launch)) : t.edit.defaultsSystem(systemName)}</div>
          <ul className="mh-rule-names">{listed.map((l, i) => <li key={i}>{l}</li>)}</ul>
          {gameOnly && more && <div className="mh-modal-note">{t.edit.defaultsMore(all.rules.length - gameRules!.rules.length, systemName)}</div>}
          <div className="mh-modal-note">{t.edit.resetBody}</div>
        </>
      }
      strOKButtonText={gameOnly ? t.edit.onlyGame(shortGameTitle(ctx.launch)) : t.edit.allGames(systemName)}
      strMiddleButtonText={gameOnly && more ? t.edit.allGames(systemName) : undefined}
      onMiddleButton={gameOnly && more ? () => run(null) : undefined}
      strCancelButtonText={t.edit.cancel}
      onCancel={ctx.refocus}
      onOK={() => run(gameOnly ? game ?? null : null)}
    />,
  );
}

export function openRules() {
  Navigation.Navigate(RULES_ROUTE);
}

// The map's ≡ menu: undo, the rules list, back to the emulator's defaults.
export function openMenu(ctx: MapContext, undoLabel: string | null) {
  showContextMenu(
    <Menu label={t.edit.menu} cancelText={t.edit.cancel}>
      {undoLabel && <MenuItem onSelected={() => undoLast()}>{t.edit.undoWhat(undoLabel)}</MenuItem>}
      <MenuItem onSelected={openRules}>{t.edit.openRules}</MenuItem>
      <MenuItem onSelected={() => backToDefaults(ctx)}>{t.edit.defaultsMenu}</MenuItem>
    </Menu>,
  );
}
