import { toaster } from "@decky/api";
import { ConfirmModal, Focusable, type GamepadEvent, Navigation, ScrollPanelGroup, showModal } from "@decky/ui";
import { useCallback, useEffect, useState } from "react";
import { FaChevronLeft, FaExclamationTriangle } from "react-icons/fa";
import { positionWords } from "../format";
import { Loading, Message } from "../States";
import { type Answer, type RuleRow, deleteRules, getRules, setRulesOn } from "../rules";
import { t } from "../strings";
import { Styles } from "../styles";

type Listing = { rules: RuleRow[]; problems: { file: string; problem: string }[] };

const goBack = () => Navigation.NavigateBack();
const reveal = (evt: GamepadEvent) => (evt.target as HTMLElement | null)?.scrollIntoView?.({ block: "nearest" });

// "C▼ on the top face button, C◀ on the left face button"; options counted, chords as written.
function summary(rule: RuleRow): string {
  const parts = rule.bindings.map((b) => `${b.label} ${positionWords(b.input)}`);
  if (rule.options) parts.push(t.rules.settings(rule.options));
  return parts.join(" · ");
}

function Row({ rule, busy, onToggle, onDelete }: {
  rule: RuleRow;
  busy: boolean;
  onToggle: () => void;
  onDelete: () => void;
}) {
  const what = summary(rule);
  return (
    <Focusable
      className="mh-rule"
      role="switch"
      aria-checked={rule.on}
      aria-label={`${rule.label || rule.id}, ${rule.scope}`}
      focusClassName="mh-focus"
      noFocusRing
      onActivate={busy ? undefined : onToggle}
      onClick={busy ? undefined : onToggle}
      onOKActionDescription={rule.on ? t.rules.off : t.rules.on}
      onSecondaryButton={onDelete}
      onSecondaryActionDescription={t.rules.delete}
      onGamepadFocus={reveal}
    >
      <div className="mh-rule-text">
        <div className="mh-rule-label">{rule.label || rule.id}</div>
        <div className="mh-rule-scope">
          {rule.scope}
          {rule.edit && <span className="mh-rule-made">{` · ${t.rules.madeHere}`}</span>}
        </div>
        {what && <div className="mh-rule-what">{what}</div>}
        {rule.clashes.map((c, i) => (
          <div key={i} className="mh-rule-clash">
            <FaExclamationTriangle aria-hidden="true" size={10} /> {c}
          </div>
        ))}
      </div>
      <span className={`mh-switch${rule.on ? " mh-switch-on" : ""}`} aria-hidden="true">
        <span className="mh-switch-knob" />
      </span>
    </Focusable>
  );
}

// Every rule in $DATA/rules and rules-off (docs/08 Flow 4): A turns one on or off, X deletes it. The N64 layouts
// parked in rules-off show up here, off.
export function RulesPage() {
  const [answer, setAnswer] = useState<Answer<Listing> | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => setAnswer(await getRules()), []);
  useEffect(() => {
    load();
  }, [load]);

  const toggle = async (rule: RuleRow) => {
    setBusy(rule.id);
    const result = await setRulesOn([rule.id], !rule.on);
    setBusy(null);
    if (!result.ok) toaster.toast({ title: t.edit.failed, body: result.error, critical: true });
    for (const warning of result.ok ? result.data.warnings : []) toaster.toast({ title: t.rules.title, body: warning });
    load();
  };

  const remove = (rule: RuleRow) => {
    showModal(
      <ConfirmModal
        strTitle={t.rules.deleteTitle}
        strDescription={t.rules.deleteBody(rule.label || rule.id)}
        strOKButtonText={t.rules.delete}
        strCancelButtonText={t.edit.cancel}
        bDestructiveWarning
        onOK={async () => {
          const result = await deleteRules([rule.id]);
          if (!result.ok) toaster.toast({ title: t.edit.failed, body: result.error, critical: true });
          load();
        }}
      />,
    );
  };

  const rules = answer?.ok ? answer.data.rules : [];
  const sorted = (on: boolean) => rules.filter((r) => r.on === on).sort((a, b) =>
    (a.system_name ?? "").localeCompare(b.system_name ?? "") || (a.label || a.id).localeCompare(b.label || b.id));
  const Scroll = ScrollPanelGroup ?? "div";

  let body;
  if (!answer) {
    body = <div className="mh-state-wrap"><Loading /></div>;
  } else if (!answer.ok) {
    body = <div className="mh-state-wrap"><Message title={t.states.errorTitle} body={answer.error} /></div>;
  } else if (!rules.length && !answer.data.problems.length) {
    body = <div className="mh-state-wrap"><Message title={t.rules.title} body={t.rules.empty} /></div>;
  } else {
    body = (
      <div className="mh-list-wrap mh-rules-wrap">
        <Scroll>
          <Focusable className="mh-rules" flow-children="column">
            {([true, false] as const).map((on) => sorted(on).length > 0 && (
              <div key={String(on)} className="mh-rules-group">
                <div className="mh-list-heading">{`${on ? t.rules.on : t.rules.off} · ${sorted(on).length}`}</div>
                {sorted(on).map((rule) => (
                  <Row key={rule.id} rule={rule} busy={busy === rule.id} onToggle={() => toggle(rule)}
                    onDelete={() => remove(rule)} />
                ))}
              </div>
            ))}
            {answer.data.problems.length > 0 && (
              <div className="mh-rules-group">
                <div className="mh-list-heading">{t.rules.problems}</div>
                {answer.data.problems.map((p) => (
                  <div key={p.file} className="mh-rule-clash">{`${p.file}: ${p.problem}`}</div>
                ))}
              </div>
            )}
          </Focusable>
        </Scroll>
      </div>
    );
  }

  return (
    <>
      <Styles />
      <Focusable className="mh-route" onCancelButton={goBack} onCancelActionDescription={t.map.goBack}>
        <div className="mh-header">
          <Focusable className="mh-icon-button" role="button" aria-label={t.map.back} focusClassName="mh-focus"
            noFocusRing onActivate={goBack} onClick={goBack}>
            <FaChevronLeft aria-hidden="true" />
          </Focusable>
          <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0, flex: 1 }}>
            <div className="mh-title">{t.rules.title}</div>
            <div className="mh-subtitle">{t.rules.subtitle}</div>
          </div>
        </div>
        <div className="mh-body mh-rules-body">{body}</div>
      </Focusable>
    </>
  );
}
