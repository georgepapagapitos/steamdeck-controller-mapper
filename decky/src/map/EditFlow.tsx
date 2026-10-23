import { toaster } from "@decky/api";
import { DialogButton, Focusable, type GamepadEvent, ModalRoot, SteamSpinner } from "@decky/ui";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { FaCheck } from "react-icons/fa";
import type { Launch, PadInput, Player } from "../data";
import { shortGameTitle, shortPadName } from "../format";
import { Glyph } from "../glyphs";
import { type Change, type EditResult, type Op, type Scope, type Target, editRules, getTargets } from "../rules";
import { t } from "../strings";
import { Styles } from "../styles";
import { type Capture, type Want, asSource, capture } from "./capture";
import { ConsolePad, hasConsolePad } from "./consoles";
import { type Control, groupControls } from "./controls";
import { PadDrawing } from "./PadDrawing";

const CAPTURE_MS = 10000;

// One job of the control being changed: an input and what it drives now (a stick's axes come as one job).
interface Job {
  input: PadInput;
  targets: { target: string; label: string }[];
}

// What gets saved: console input <- physical input.
interface Bind {
  target: string;
  label: string;
  source: string;
}

type Step =
  | { kind: "pick" }
  | { kind: "job"; job: Job }
  | { kind: "capture"; job: Job; want: Want; message?: string; stopped?: boolean }
  | { kind: "confirm"; job: Job; want: Want; pressed: string }
  | { kind: "scope"; binds: Bind[] }
  | { kind: "result"; result: EditResult };

export interface EditProps {
  closeModal?: () => void; // given by showModal
  launch: Launch;
  player: Player;
  players: Player[];
  control: Control;
  prefix: string;
  onSaved: (delta: number) => void;
}

const named = (prefix: string, label: string) => (prefix ? `${prefix} ${label}` : label);
const isAxis = (target: string) => /_(x|y)$/.test(target);
const TRIGGER_TARGETS = /^(l|r)(_analog|_trigger|2)$/;

function wantFor(job: Job): Want {
  const target = job.targets[0]?.target.split(".").pop() ?? "";
  if (isAxis(target)) return target.endsWith("_x") ? "stick-x" : "stick-y";
  return TRIGGER_TARGETS.test(target) && job.targets.length === 1 && /^(l|r)2$/.test(job.input.input) ? "trigger" : "button";
}

// A stick's axes are one job (moved together); every other console input is a job of its own, so a stick that
// gives four C buttons offers four.
export function jobsOf(control: Control): Job[] {
  return control.inputs.flatMap((input) => {
    const seen = new Map<string, string>();
    for (const drive of input.drives) seen.set(drive.target, drive.label);
    const all = [...seen].map(([target, label]) => ({ target, label }));
    const axes = all.filter((x) => isAxis(x.target));
    const jobs: Job[] = all.filter((x) => !isAxis(x.target)).map((x) => ({ input, targets: [x] }));
    if (axes.length) jobs.unshift({ input, targets: axes });
    return jobs.length ? jobs : [{ input, targets: [] }];
  });
}

// "Assign" choices: console inputs for a button, a pair of axes (both at once) for a stick. The question
// names the system, so the labels go without its prefix.
function jobChoices(targets: Target[], input: string): { key: string; text: string; binds: Bind[] }[] {
  const stick = input === "ls" || input === "rs";
  if (!stick) {
    return targets.filter((x) => x.kind !== "axis").map((x) => ({
      key: x.target, text: x.label, binds: [{ target: x.target, label: x.label, source: input }],
    }));
  }
  return targets.filter((x) => x.kind === "axis" && x.target.endsWith("_x")).flatMap((x) => {
    const y = targets.find((o) => o.target === `${x.target.slice(0, -2)}_y`);
    if (!y) return [];
    const text = x.label.replace(/\s*X$/, "");
    return [{ key: x.target, text, binds: [{ target: x.target, label: x.label, source: `${input}_x` },
                                          { target: y.target, label: y.label, source: `${input}_y` }] }];
  });
}

// The drawing's control for a physical input: a stick half or axis is its stick's control.
function controlKeyFor(controls: Control[], input: string): string | null {
  return controls.find((c) => c.inputs.some((i) => i.input === input || input.startsWith(`${i.input}_`)))?.key ?? null;
}

// A physical input in this player's own words: its glyph and name, a stick half or axis as the stick's glyph.
export function inputWords(player: Player, input: string): { glyph: string; name: string } {
  const row = player.inputs.find((r) => r.input === input);
  if (row) return { glyph: row.glyph, name: row.name };
  const part = input.match(/^(ls|rs)_(up|down|left|right|x|y)$/);
  const stick = part && player.inputs.find((r) => r.input === part[1]);
  if (part && stick) {
    const how = part[2] === "x" || part[2] === "y" ? t.edit.stickWords[part[2]] : part[2];
    return { glyph: stick.glyph, name: `${stick.name} ${how}` };
  }
  return { glyph: input, name: input };
}

function GlyphName({ player, input, size = 22 }: { player: Player; input: string; size?: number }) {
  const { glyph, name } = inputWords(player, input);
  return (
    <span className="mh-glyph-name">
      <Glyph pad={player.pad} label={glyph} size={size} className="mh-glyph" />
      <span>{name}</span>
    </span>
  );
}

// The changes a save makes (or made), per player, in each player's own glyphs when that player is known.
export function ChangeList({ changes, players }: { changes: Change[]; players: Player[] }) {
  const groups = new Map<number, Change[]>();
  for (const change of changes) groups.set(change.player, [...(groups.get(change.player) ?? []), change]);
  return (
    <div className="mh-changes">
      {[...groups].map(([n, rows]) => {
        const known = players.find((p) => p.player === n && p.pad.name === rows[0].pad);
        return (
          <div key={n} className="mh-change-group">
            <div className="mh-change-player">{t.edit.playerShort(n, shortPadName(rows[0].pad))}</div>
            {rows.map((c) => (
              <div key={c.input} className="mh-change">
                {known ? <Glyph pad={known.pad} label={c.glyph} size={20} className="mh-glyph" />
                  : <span className="mh-glyph">{c.glyph}</span>}
                <span className="mh-change-was">{c.before.join(", ") || t.map.nothing}</span>
                <span aria-hidden="true">→</span>
                <span className="mh-change-now">{c.after.join(", ") || t.map.nothing}</span>
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}

function Buttons({ children }: { children: ReactNode }) {
  return <Focusable className="mh-modal-buttons" flow-children="row">{children}</Focusable>;
}

function Button({ onClick, children, disabled }: { onClick: () => void; children: ReactNode; disabled?: boolean }) {
  return (
    <DialogButton className="mh-modal-button" onClick={onClick} disabled={disabled}>
      {children}
    </DialogButton>
  );
}

// The capture screen: one focused element that swallows every button (so nothing navigates or closes the modal)
// and hands its UI events to the capture as the fallback source.
// The capture screen: one focused element that swallows every button (so nothing navigates or closes the modal)
// and hands its UI events to the capture as the fallback source. Beside the title: the console's pad with the
// input being changed lit, and the player's pad with the button that does it now outlined; a press lights the
// pressed button there for a moment before the flow moves on.
function CaptureView({ title, hint, message, consolePad, pad, onPress, onTimeout, want }: {
  title: string;
  hint: string;
  message?: string;
  consolePad: ReactNode;
  pad: (pressed: string | null) => ReactNode;
  want: Want;
  onPress: (input: string) => void;
  onTimeout: () => void;
}) {
  const handle = useRef<Capture | null>(null);
  const [left, setLeft] = useState(CAPTURE_MS);
  const [pressed, setPressed] = useState<string | null>(null);
  useEffect(() => {
    let flash: ReturnType<typeof setTimeout> | null = null;
    handle.current = capture(want, (input) => {
      setPressed(input);
      flash = setTimeout(() => onPress(input), 450);
    });
    const started = Date.now();
    const tick = setInterval(() => {
      const rest = CAPTURE_MS - (Date.now() - started);
      setLeft(Math.max(rest, 0));
      if (rest <= 0) {
        clearInterval(tick);
        handle.current?.stop();
        onTimeout();
      }
    }, 100);
    return () => {
      clearInterval(tick);
      if (flash) clearTimeout(flash);
      handle.current?.stop();
    };
  }, []);
  const swallow = (evt: GamepadEvent) => {
    handle.current?.uiButton(evt.detail.button);
    evt.preventDefault?.();
    evt.stopPropagation?.();
  };
  return (
    <Focusable
      className="mh-capture"
      focusClassName="mh-capture-on"
      noFocusRing
      onButtonDown={swallow}
      onCancelButton={swallow}
      onOKButton={swallow}
      onSecondaryButton={swallow}
      onOptionsButton={swallow}
      onMenuButton={swallow}
      onGamepadDirection={swallow}
      onCancel={(evt: GamepadEvent) => evt?.stopPropagation?.()}
      role="status"
      aria-live="assertive"
    >
      <div className="mh-modal-title">{title}</div>
      <div className="mh-capture-pads">
        {consolePad && <div className="mh-capture-pane">{consolePad}</div>}
        <div className="mh-capture-pane">{pad(pressed)}</div>
      </div>
      {message && <div className="mh-modal-warn">{message}</div>}
      <div className="mh-modal-note">{hint}</div>
      <div className="mh-capture-bar" aria-hidden="true">
        <div style={{ width: `${(left / CAPTURE_MS) * 100}%` }} />
      </div>
    </Focusable>
  );
}

function scopeOf(launch: Launch, player: Player, games: "game" | "system", pads: "any" | "family" | "device"): Scope {
  const content: Scope["content"] = games === "game" && launch.game
    ? { level: "game", system: launch.system, game_id: launch.game }
    : { level: "system", system: launch.system };
  const controller: Scope["controller"] =
    pads === "family" && player.pad.family ? { level: "family", value: player.pad.family }
    : pads === "device" ? { level: "device", player: player.player, model: player.pad.model }
    : { level: "any" };
  return { controller, content };
}

function Choice<T extends string>({ value, options, onChange, label }: {
  value: T;
  options: { value: T; text: string }[];
  onChange: (value: T) => void;
  label: string;
}) {
  return (
    <div className="mh-choice">
      <div className="mh-choice-label">{label}</div>
      <Focusable className="mh-choice-row" flow-children="row" aria-label={label}>
        {options.map((o) => (
          <DialogButton
            key={o.value}
            className={`mh-chip-button${o.value === value ? " mh-chip-on" : ""}`}
            onClick={() => onChange(o.value)}
          >
            {o.value === value && <FaCheck className="mh-chip-check" aria-hidden="true" size={11} />}
            {o.text}
            {o.value === value && <span className="mh-sr-only">{` (${t.edit.chosen})`}</span>}
          </DialogButton>
        ))}
      </Focusable>
    </div>
  );
}

function ScopeView({ launch, player, players, binds, onBack, onSaved }: {
  launch: Launch;
  player: Player;
  players: Player[];
  binds: Bind[];
  onBack: () => void;
  onSaved: (result: EditResult) => void;
}) {
  const [games, setGames] = useState<"game" | "system">(launch.game ? "game" : "system");
  const [pads, setPads] = useState<"any" | "family" | "device">("any");
  const [preview, setPreview] = useState<{ busy: boolean; result?: EditResult; error?: string }>({ busy: true });
  const [saving, setSaving] = useState(false);
  const request = useRef(0);
  const ops: Op[] = useMemo(() => {
    const scope = scopeOf(launch, player, games, pads);
    return binds.map((b) => ({ op: "set", target: b.target, source: { input: b.source }, scope }));
  }, [games, pads]);

  useEffect(() => {
    const id = ++request.current;
    setPreview((p) => ({ ...p, busy: true }));
    editRules(ops, true).then((answer) => {
      if (id !== request.current) return;
      setPreview(answer.ok ? { busy: false, result: answer.data } : { busy: false, error: answer.error });
    });
  }, [ops]);

  const save = async () => {
    setSaving(true);
    const answer = await editRules(ops);
    setSaving(false);
    if (answer.ok) onSaved(answer.data);
    else setPreview({ busy: false, error: answer.error });
  };

  const short = shortPadName(player.pad.name);
  const system = launch.system_name || launch.system.toUpperCase();
  const padOptions: { value: "any" | "family" | "device"; text: string }[] = [{ value: "any", text: t.edit.anyPad }];
  if (player.pad.family && player.pad.shape !== "deck") padOptions.push({ value: "family", text: t.edit.familyPads(short) });
  padOptions.push({ value: "device", text: t.edit.onePad(short, player.player) });
  const changes = preview.result?.changes;

  return (
    <>
      <div className="mh-modal-title">{t.edit.whereTitle}</div>
      {launch.game && (
        <Choice label={t.edit.games} value={games} onChange={setGames}
          options={[{ value: "game", text: t.edit.thisGame(shortGameTitle(launch)) },
                    { value: "system", text: t.edit.allGames(system) }]} />
      )}
      <Choice label={t.edit.pads} value={pads} onChange={setPads} options={padOptions} />
      <div className="mh-choice-label">{t.edit.preview}</div>
      <div className="mh-preview" aria-live="polite">
        {preview.busy ? (
          <div className="mh-modal-note">{t.edit.previewing}</div>
        ) : preview.error ? (
          <div className="mh-modal-warn">{preview.error}</div>
        ) : changes == null ? (
          <div className="mh-modal-note">{t.edit.previewError(preview.result?.preview_error ?? "")}</div>
        ) : changes.length === 0 ? (
          <div className="mh-modal-note">{t.edit.previewNone}</div>
        ) : (
          <ChangeList changes={changes} players={players} />
        )}
      </div>
      <Buttons>
        <Button onClick={save} disabled={saving}>{saving ? t.edit.saving : t.edit.save}</Button>
        <Button onClick={onBack}>{t.edit.back}</Button>
      </Buttons>
    </>
  );
}

export function ResultView({ result, players, onUndo, onDone, title = t.edit.saved }: {
  result: EditResult;
  players: Player[];
  onUndo: () => void;
  onDone: () => void;
  title?: string;
}) {
  const [undoing, setUndoing] = useState(false);
  return (
    <>
      <div className="mh-modal-title">{title}</div>
      <div className="mh-modal-note">{t.edit.savedBody}</div>
      <div className="mh-preview">
        {result.changes && result.changes.length > 0 ? <ChangeList changes={result.changes} players={players} />
          : <div className="mh-modal-note">{result.changes ? t.edit.nothingChanged : t.edit.previewError(result.preview_error ?? "")}</div>}
      </div>
      <Buttons>
        <Button onClick={onDone}>{t.edit.done}</Button>
        <Button disabled={undoing} onClick={() => { setUndoing(true); onUndo(); }}>{t.edit.undo}</Button>
      </Buttons>
    </>
  );
}

// Undo a saved edit: its undo ops are themselves an edit. Toasts the outcome.
export async function undoEdit(result: EditResult, onSaved: (delta: number) => void) {
  const answer = await editRules(result.undo);
  if (answer.ok) {
    onSaved(-1);
    toaster.toast({ title: t.title, body: t.edit.undone });
  } else {
    toaster.toast({ title: t.edit.failed, body: answer.error, critical: true });
  }
}

// "Change button" for one control of one player (docs/08 Flow 2, principle 1: intent first, scope after).
export function EditFlow({ closeModal, launch, player, players, control, prefix, onSaved }: EditProps) {
  const jobs = useMemo(() => jobsOf(control), [control]);
  const first = (job: Job): Step =>
    job.targets.length ? { kind: "capture", job, want: wantFor(job) } : { kind: "job", job };
  const [step, setStep] = useState<Step>(jobs.length === 1 ? first(jobs[0]) : { kind: "pick" });
  const [targets, setTargets] = useState<Target[] | null>(null);
  const capturing = step.kind === "capture" && !step.stopped;
  const controls = useMemo(() => groupControls(player.inputs), [player]);
  const close = () => closeModal?.();

  useEffect(() => {
    if (step.kind === "job" && !targets) getTargets(launch.system).then((a) => setTargets(a.ok ? a.data.targets : []));
  }, [step.kind]);

  let body: ReactNode;
  if (step.kind === "pick") {
    body = (
      <>
        <div className="mh-modal-title">{t.edit.whichOne}</div>
        <Focusable className="mh-modal-list" flow-children="column">
          {jobs.map((job) => (
            <DialogButton key={`${job.input.input}:${job.targets[0]?.target ?? ""}`} className="mh-job"
              onClick={() => setStep(first(job))}>
              <GlyphName player={player} input={job.input.input} />
              <span className="mh-job-what">
                {job.targets.length ? job.targets.map((x) => named(prefix, x.label)).join(", ") : t.edit.doesNothing}
              </span>
            </DialogButton>
          ))}
        </Focusable>
      </>
    );
  } else if (step.kind === "job") {
    const { glyph } = inputWords(player, step.job.input.input);
    const choices = jobChoices(targets ?? [], step.job.input.input);
    body = (
      <>
        <div className="mh-modal-title mh-title-glyph">
          <Glyph pad={player.pad} label={glyph} size={26} className="mh-glyph" />
          <span>{t.edit.whatShould(launch.system_name || launch.system.toUpperCase())}</span>
        </div>
        {!targets ? <SteamSpinner background="transparent" style={{ height: 40 }} /> : (
          <Focusable className="mh-target-grid" flow-children="grid">
            {choices.map((c, i) => (
              <DialogButton key={c.key} className="mh-target" preferredFocus={i === 0}
                onClick={() => setStep({ kind: "scope", binds: c.binds })}>
                {c.text}
              </DialogButton>
            ))}
          </Focusable>
        )}
        {targets && (
          <Buttons>
            <Button onClick={() => (jobs.length > 1 ? setStep({ kind: "pick" }) : close())}>{t.edit.cancel}</Button>
          </Buttons>
        )}
      </>
    );
  } else if (step.kind === "capture") {
    const what = step.job.targets.map((x) => named(prefix, x.label)).join(", ");
    const title = step.want === "button" ? t.edit.pressFor(what)
      : step.want === "trigger" ? t.edit.pullFor(what) : t.edit.moveFor(what);
    const lit = step.job.targets.map((x) => x.target);
    const consolePad = <ConsolePad system={launch.system} lit={lit} label={t.edit.consolePad(what)} />;
    const current = controlKeyFor(controls, step.job.input.input);
    if (step.stopped) {
      body = (
        <>
          <div className="mh-modal-title">{title}</div>
          <div className="mh-modal-warn">{t.edit.nothingPressed}</div>
          <Buttons>
            <Button onClick={() => setStep({ kind: "capture", job: step.job, want: step.want })}>{t.edit.tryAgain}</Button>
            <Button onClick={close}>{t.edit.cancel}</Button>
          </Buttons>
        </>
      );
    } else {
      body = (
        <CaptureView
          key={step.message ?? "first"}
          title={title}
          hint={t.edit.pressHint}
          message={step.message}
          want={step.want}
          consolePad={hasConsolePad(launch.system) ? consolePad : null}
          pad={(pressed) => (
            <PadDrawing pad={player.pad} controls={controls}
              selected={pressed ? controlKeyFor(controls, pressed) : current}
              outlined={pressed ? null : current} />
          )}
          onTimeout={() => setStep({ ...step, stopped: true })}
          onPress={(pressed) => setStep({ kind: "confirm", job: step.job, want: step.want, pressed })}
        />
      );
    }
  } else if (step.kind === "confirm") {
    const { job, want, pressed } = step;
    const source = asSource(pressed, want);
    const words = inputWords(player, pressed);
    const steamOnly = player.inputs.find((r) => r.input === pressed)?.steam_only || /^paddle/.test(pressed);
    const retry = (message?: string) => setStep({ kind: "capture", job, want, message });
    const binds: Bind[] = job.targets.map((x) => ({
      target: x.target, label: x.label,
      source: want === "button" ? (source ?? pressed) : `${(source ?? "").slice(0, 2)}_${x.target.endsWith("_x") ? "x" : "y"}`,
    }));
    // The pressed button's own job, when it has exactly one: then a swap is the likely intent.
    const row = player.inputs.find((r) => r.input === pressed);
    const its = row && !row.steam_only ? [...new Set(row.drives.map((d) => d.target))] : [];
    const theirs = its.length === 1 ? row!.drives.find((d) => d.target === its[0])! : null;
    const swappable = want === "button" && theirs && job.targets.length === 1 && pressed !== job.input.input
      && !job.targets.some((x) => x.target === theirs.target) && !/^(ls|rs)$/.test(job.input.input);
    const problem = steamOnly ? t.edit.steamOnly(words.glyph)
      : source === null ? (want === "trigger" ? t.edit.notTrigger : t.edit.notStick)
      : null;
    body = (
      <>
        <div className="mh-modal-title">{t.edit.youPressed}</div>
        <div className="mh-pressed"><GlyphName player={player} input={pressed} size={40} /></div>
        {problem && <div className="mh-modal-warn">{problem}</div>}
        {!problem && theirs && (
          <div className="mh-modal-note">{t.edit.already(words.glyph, named(prefix, theirs.label))}</div>
        )}
        <Buttons>
          {!problem && swappable && theirs && (
            <Button onClick={() => setStep({ kind: "scope", binds: [...binds,
              { target: theirs.target, label: theirs.label, source: job.input.input }] })}>
              {t.edit.swap(named(prefix, theirs.label), job.input.glyph)}
            </Button>
          )}
          {!problem && (
            <Button onClick={() => setStep({ kind: "scope", binds })}>
              {theirs ? t.edit.both(words.glyph) : t.edit.use(words.glyph)}
            </Button>
          )}
          <Button onClick={() => retry()}>{t.edit.pressAgain}</Button>
          <Button onClick={close}>{t.edit.cancel}</Button>
        </Buttons>
      </>
    );
  } else if (step.kind === "scope") {
    body = (
      <ScopeView launch={launch} player={player} players={players} binds={step.binds}
        onBack={() => setStep(jobs.length === 1 ? first(jobs[0]) : { kind: "pick" })}
        onSaved={(result) => {
          onSaved(1);
          setStep({ kind: "result", result });
        }} />
    );
  } else {
    const { result } = step;
    body = (
      <ResultView result={result} players={players} onDone={close}
        onUndo={() => undoEdit(result, onSaved).then(close)} />
    );
  }

  // While capturing, B is a button to capture, not "close": only the capture screen's own timeout ends it.
  return (
    <ModalRoot onCancel={capturing ? undefined : close} closeModal={capturing ? undefined : close} bAllowFullSize>
      <Styles />
      <div className="mh-modal" aria-label={t.edit.changeFor(named(prefix, control.name))}>{body}</div>
    </ModalRoot>
  );
}
