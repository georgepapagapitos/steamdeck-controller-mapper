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
      onSaved={(result, where, what) => {
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

// Turn off the rules for this game, or for every game of the system: a dry run lists them first.
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
      }}
    />,
  );
}

export function openRules() {
  Navigation.Navigate(RULES_ROUTE);
}

// The map's ≡ menu: undo, the rules list, the resets.
export function openMenu(ctx: MapContext, undoLabel: string | null) {
  const system = ctx.launch.system_name || ctx.launch.system.toUpperCase();
  showContextMenu(
    <Menu label={t.edit.menu} cancelText={t.edit.cancel}>
      {undoLabel && <MenuItem onSelected={() => undoLast()}>{t.edit.undoWhat(undoLabel)}</MenuItem>}
      <MenuItem onSelected={openRules}>{t.edit.openRules}</MenuItem>
      {ctx.launch.game && (
        <MenuItem onSelected={() => reset(ctx, ctx.launch.game ?? null)}>
          {t.edit.resetGame(shortGameTitle(ctx.launch))}
        </MenuItem>
      )}
      <MenuItem tone="destructive" onSelected={() => reset(ctx, null)}>{t.edit.resetSystem(system)}</MenuItem>
    </Menu>,
  );
}
