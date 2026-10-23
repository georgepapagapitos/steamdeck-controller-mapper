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

// pick: which of the control's jobs (only when it has several); assign: what a button that does nothing should do;
// capture: wait for a press; decide: what changes, and where to save it.
type Step =
  | { kind: "pick" }
  | { kind: "assign"; job: Job }
  | { kind: "capture"; job: Job; want: Want; stopped?: boolean }
  | { kind: "decide"; job: Job; want: Want; pressed: string; binds: Bind[]; back: Step };

export type Where = "game" | "system" | "pad";

export interface EditProps {
  closeModal?: () => void; // given by showModal
  launch: Launch;
  player: Player;
  players: Player[];
  control: Control;
  prefix: string;
  onSaved: (result: EditResult, where: Where, what: string) => void;
  onClosed?: () => void; // focus goes back to the map's row
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


function Buttons({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <Focusable className={`mh-modal-buttons ${className}`} flow-children="row">{children}</Focusable>;
}

function Button({ onClick, children, disabled, primary, focus }: {
  onClick: () => void;
  children: ReactNode;
  disabled?: boolean;
  primary?: boolean;
  focus?: boolean;
}) {
  return (
    <DialogButton className={`mh-modal-button${primary ? " mh-primary" : ""}${focus ? " mh-first" : ""}`}
      onClick={onClick} disabled={disabled} preferredFocus={focus}>
      {children}
    </DialogButton>
  );
}

// The capture screen: one focused element that swallows every button (so nothing navigates or closes the modal)
// and hands its UI events to the capture as the fallback source. The console's pad with the input being changed
// lit, beside the player's pad with the button that does it now ringed; a press lights the pressed button for a
// moment before the flow moves on.
function CaptureView({ title, consolePad, pad, onPress, onTimeout, want }: {
  title: string;
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
      <div className="mh-modal-note">{t.edit.pressHint}</div>
      <div className="mh-capture-bar" aria-hidden="true">
        <div style={{ width: `${(left / CAPTURE_MS) * 100}%` }} />
      </div>
    </Focusable>
  );
}

export function scopeOf(launch: Launch, player: Player, where: Where): Scope {
  if (where === "pad") {
    return { controller: { level: "device", player: player.player, model: player.pad.model },
             content: { level: "system", system: launch.system } };
  }
  return {
    controller: { level: "any" },
    content: where === "game" && launch.game ? { level: "game", system: launch.system, game_id: launch.game }
      : { level: "system", system: launch.system },
  };
}

// What changes and where to save it, on one screen. The pressed button's own job moves to the old button (a
// swap) when that's a plain button; "Keep both" turns that off. The three save buttons are the scope: this game,
// all of the system's games, or this one controller (in all of the system's games). The preview is a dry run for
// the pads connected now.
function DecideView({ launch, player, players, prefix, step, onSaved, onAgain, onBack, onCancel }: {
  launch: Launch;
  player: Player;
  players: Player[];
  prefix: string;
  step: Extract<Step, { kind: "decide" }>;
  onSaved: (result: EditResult, where: Where) => void;
  onAgain?: () => void;
  onBack?: () => void;
  onCancel: () => void;
}) {
  const { job, want, pressed, binds } = step;
  const words = inputWords(player, pressed);
  const source = want === "button" ? pressed : asSource(pressed, want);
  const row = player.inputs.find((r) => r.input === pressed);
  const steamOnly = row?.steam_only || /^paddle/.test(pressed);
  const problem = steamOnly ? t.edit.steamOnly(words.glyph)
    : source === null ? (want === "trigger" ? t.edit.notTrigger : t.edit.notStick)
    : pressed === job.input.input && job.targets.length ? t.edit.sameButton(words.glyph)
    : null;
  // The pressed button's own job, when it has exactly one other than this one: a swap is the likely intent.
  const its = row && !row.steam_only ? [...new Set(row.drives.map((d) => d.target))] : [];
  const theirs = its.length === 1 && !binds.some((b) => b.target === its[0])
    ? row!.drives.find((d) => d.target === its[0])! : null;
  const canSwap = !!theirs && want === "button" && job.targets.length === 1 && !/^(ls|rs)$/.test(job.input.input);
  const [swap, setSwap] = useState(true);
  const all: Bind[] = canSwap && swap ? [...binds, { target: theirs!.target, label: theirs!.label, source: job.input.input }]
    : binds;
  const [preview, setPreview] = useState<{ busy: boolean; result?: EditResult; error?: string }>({ busy: true });
  const [saving, setSaving] = useState<Where | null>(null);
  const request = useRef(0);
  const opsFor = (where: Where): Op[] => {
    const scope = scopeOf(launch, player, where);
    return all.map((b) => ({ op: "set", target: b.target, source: { input: b.source }, scope }));
  };

  useEffect(() => {
    if (problem) return;
    const id = ++request.current;
    setPreview((p) => ({ ...p, busy: true }));
    editRules(opsFor(launch.game ? "game" : "system"), true).then((answer) => {
      if (id !== request.current) return;
      setPreview(answer.ok ? { busy: false, result: answer.data } : { busy: false, error: answer.error });
    });
  }, [swap]);

  const save = async (where: Where) => {
    setSaving(where);
    const answer = await editRules(opsFor(where));
    setSaving(null);
    if (answer.ok) onSaved(answer.data, where);
    else setPreview({ busy: false, error: answer.error });
  };

  const what = binds.map((b) => named(prefix, b.label)).join(", ");
  // Where the console input is now: a binding moves it (one physical input per console input), so say so.
  const from = player.inputs.find((r) => !r.steam_only && r.drives.some((d) => d.target === binds[0]?.target));
  const changes = preview.result?.changes;
  const short = shortPadName(player.pad.name);
  const system = launch.system_name || launch.system.toUpperCase();
  return (
    <>
      <div className="mh-decide">
        <Glyph pad={player.pad} label={words.glyph} size={40} className="mh-glyph" />
        <span className="mh-decide-arrow" aria-hidden="true">→</span>
        <span className="mh-decide-what">{what}</span>
      </div>
      <div className="mh-modal-note">
        {from && from.input !== pressed ? t.edit.moves(what, from.glyph, words.glyph) : t.edit.decideLine(words.glyph, what)}
      </div>
      {problem ? <div className="mh-modal-warn">{problem}</div> : (
        <>
          {canSwap && (
            <Focusable className="mh-swap" flow-children="row">
              <DialogButton className={`mh-chip-button${swap ? " mh-chip-on" : ""}`} onClick={() => setSwap(true)}>
                {swap && <FaCheck aria-hidden="true" size={11} />}
                {t.edit.swap(named(prefix, theirs!.label), job.input.glyph)}
              </DialogButton>
              <DialogButton className={`mh-chip-button${!swap ? " mh-chip-on" : ""}`} onClick={() => setSwap(false)}>
                {!swap && <FaCheck aria-hidden="true" size={11} />}
                {t.edit.both(words.glyph, named(prefix, theirs!.label))}
              </DialogButton>
            </Focusable>
          )}
          <div className="mh-choice-label">{t.edit.preview}</div>
          <div className="mh-preview" aria-live="polite">
            {preview.busy ? <div className="mh-modal-note">{t.edit.previewing}</div>
              : preview.error ? <div className="mh-modal-warn">{preview.error}</div>
              : changes == null ? <div className="mh-modal-note">{t.edit.previewError(preview.result?.preview_error ?? "")}</div>
              : changes.length === 0 ? <div className="mh-modal-note">{t.edit.previewNone}</div>
              : <ChangeList changes={changes} players={players} />}
          </div>
          <div className="mh-choice-label">{t.edit.saveFor}</div>
          <Buttons className="mh-save-row">
            {launch.game && (
              <Button primary focus onClick={() => save("game")} disabled={!!saving}>
                {saving === "game" ? t.edit.saving : t.edit.thisGame(shortGameTitle(launch))}
              </Button>
            )}
            <Button primary focus={!launch.game} onClick={() => save("system")} disabled={!!saving}>
              {saving === "system" ? t.edit.saving : t.edit.allGames(system)}
            </Button>
            <Button primary onClick={() => save("pad")} disabled={!!saving}>
              {saving === "pad" ? t.edit.saving : t.edit.onePad(short)}
            </Button>
          </Buttons>
        </>
      )}
      <Buttons>
        {onAgain && <Button onClick={onAgain} focus={!!problem}>{t.edit.pressAgain}</Button>}
        {onBack && <Button onClick={onBack} focus={!!problem && !onAgain}>{t.edit.back}</Button>}
        <Button onClick={onCancel}>{t.edit.cancel}</Button>
      </Buttons>
    </>
  );
}

// "Change button" / "Assign" for one control of one player (docs/08 Flow 2, principle 1: intent first, scope at
// save). Capture, then one screen that shows what changes and saves it where you say.
export function EditFlow({ closeModal, launch, player, players, control, prefix, onSaved, onClosed }: EditProps) {
  const jobs = useMemo(() => jobsOf(control), [control]);
  const first = (job: Job): Step =>
    job.targets.length ? { kind: "capture", job, want: wantFor(job) } : { kind: "assign", job };
  const [step, setStep] = useState<Step>(jobs.length === 1 ? first(jobs[0]) : { kind: "pick" });
  const [targets, setTargets] = useState<Target[] | null>(null);
  const capturing = step.kind === "capture" && !step.stopped;
  const controls = useMemo(() => groupControls(player.inputs), [player]);
  const close = () => {
    closeModal?.();
    onClosed?.();
  };

  useEffect(() => {
    if (step.kind === "assign" && !targets) getTargets(launch.system).then((a) => setTargets(a.ok ? a.data.targets : []));
  }, [step.kind]);

  let body: ReactNode;
  if (step.kind === "pick") {
    body = (
      <>
        <div className="mh-modal-title">{t.edit.whichOne}</div>
        <Focusable className="mh-modal-list" flow-children="column">
          {jobs.map((job, i) => (
            <DialogButton key={`${job.input.input}:${job.targets[0]?.target ?? ""}`} className={`mh-job${i === 0 ? " mh-first" : ""}`}
              preferredFocus={i === 0} onClick={() => setStep(first(job))}>
              <GlyphName player={player} input={job.input.input} />
              <span className="mh-job-what">
                {job.targets.length ? job.targets.map((x) => named(prefix, x.label)).join(", ") : t.edit.doesNothing}
              </span>
            </DialogButton>
          ))}
        </Focusable>
      </>
    );
  } else if (step.kind === "assign") {
    const { glyph } = inputWords(player, step.job.input.input);
    const job = step.job;
    const choices = jobChoices(targets ?? [], job.input.input);
    body = (
      <>
        <div className="mh-modal-title mh-title-glyph">
          <Glyph pad={player.pad} label={glyph} size={26} className="mh-glyph" />
          <span>{t.edit.whatShould(launch.system_name || launch.system.toUpperCase())}</span>
        </div>
        {!targets ? <SteamSpinner background="transparent" style={{ height: 40 }} /> : (
          <>
            <Focusable className="mh-target-grid" flow-children="grid">
              {choices.map((c, i) => (
                <DialogButton key={c.key} className={`mh-target${i === 0 ? " mh-first" : ""}`} preferredFocus={i === 0}
                  onClick={() => setStep({ kind: "decide", job,
                    want: "button", pressed: job.input.input, binds: c.binds, back: step })}>
                  {c.text}
                </DialogButton>
              ))}
            </Focusable>
            <Buttons><Button onClick={() => (jobs.length > 1 ? setStep({ kind: "pick" }) : close())}>{t.edit.cancel}</Button></Buttons>
          </>
        )}
      </>
    );
  } else if (step.kind === "capture") {
    const what = step.job.targets.map((x) => named(prefix, x.label)).join(", ");
    const title = step.want === "button" ? t.edit.pressFor(what)
      : step.want === "trigger" ? t.edit.pullFor(what) : t.edit.moveFor(what);
    const lit = step.job.targets.map((x) => x.target);
    const current = controlKeyFor(controls, step.job.input.input);
    if (step.stopped) {
      body = (
        <>
          <div className="mh-modal-title">{title}</div>
          <div className="mh-modal-warn">{t.edit.nothingPressed}</div>
          <Buttons>
            <Button focus onClick={() => setStep({ kind: "capture", job: step.job, want: step.want })}>{t.edit.tryAgain}</Button>
            <Button onClick={close}>{t.edit.cancel}</Button>
          </Buttons>
        </>
      );
    } else {
      body = (
        <CaptureView
          title={title}
          want={step.want}
          consolePad={hasConsolePad(launch.system)
            ? <ConsolePad system={launch.system} lit={lit} label={t.edit.consolePad(what)} /> : null}
          pad={(pressed) => (
            <PadDrawing pad={player.pad} controls={controls}
              selected={pressed ? controlKeyFor(controls, pressed) : current} outlined={pressed ? null : current} />
          )}
          onTimeout={() => setStep({ ...step, stopped: true })}
          onPress={(pressed) => {
            const source = step.want === "button" ? pressed : asSource(pressed, step.want);
            const binds: Bind[] = step.job.targets.map((x) => ({
              target: x.target, label: x.label,
              source: step.want === "button" ? pressed
                : `${(source ?? "").slice(0, 2)}_${x.target.endsWith("_x") ? "x" : "y"}`,
            }));
            setStep({ kind: "decide", job: step.job, want: step.want, pressed, binds, back: step });
          }}
        />
      );
    }
  } else {
    const captured = step.back.kind === "capture";
    body = (
      <DecideView launch={launch} player={player} players={players} prefix={prefix} step={step}
        onAgain={captured ? () => setStep({ kind: "capture", job: step.job, want: step.want }) : undefined}
        onBack={captured ? undefined : () => setStep(step.back)}
        onCancel={close}
        onSaved={(result, where) => {
          close();
          onSaved(result, where, step.binds.map((b) => named(prefix, b.label)).join(", "));
        }} />
    );
  }

  // Each step's first choice takes focus when the step appears: the button that led here is gone, and Steam
  // doesn't move focus into the new step by itself. The capture screen focuses its own element.
  const root = useRef<HTMLDivElement>(null);
  const stepKey = step.kind === "capture" ? `capture:${!!step.stopped}` : step.kind;
  const hasTargets = !!targets;
  useEffect(() => {
    const id = setTimeout(() => {
      const el = root.current?.querySelector<HTMLElement>(".mh-first")
        ?? root.current?.querySelector<HTMLElement>(".mh-capture, .DialogButton");
      el?.focus();
    }, 60);
    return () => clearTimeout(id);
  }, [stepKey, hasTargets]);

  // While capturing, B is a button to capture, not "close": the capture screen's timeout is the way out.
  return (
    <ModalRoot onCancel={capturing ? undefined : close} closeModal={capturing ? undefined : close} bAllowFullSize>
      <Styles />
      <div className="mh-modal" ref={root} aria-label={t.edit.changeFor(named(prefix, control.name))}>{body}</div>
    </ModalRoot>
  );
}
