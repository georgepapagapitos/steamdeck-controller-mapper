import { toaster, useQuickAccessVisible } from "@decky/api";
import { ButtonItem, Field, PanelSection, PanelSectionRow } from "@decky/ui";
import { useEffect, useState } from "react";
import { FaExclamationTriangle } from "react-icons/fa";
import { type HealthProblem, getHealth, repairHooks } from "../rules";
import { t } from "../strings";

// Only what stops map-helper (or every controller) working, at the top of the panel: its launch hooks gone (an
// EmuDeck update or an SRM run can undo them), with one press to put them back, and Steam Input turned off for an
// emulator shortcut. Nothing when all is well. Checked each time the panel opens.
export function Health() {
  const visible = useQuickAccessVisible();
  const [problems, setProblems] = useState<HealthProblem[]>([]);
  const [repairing, setRepairing] = useState(false);
  const check = () => getHealth().then((a) => setProblems(a.ok ? a.data.problems : []));
  useEffect(() => {
    if (visible) check();
  }, [visible]);
  if (problems.length === 0) return null;
  const hooks = problems.some((p) => p.check === "launch-hooks");
  const repair = async () => {
    setRepairing(true);
    const answer = await repairHooks();
    setRepairing(false);
    toaster.toast(answer.ok ? { title: t.title, body: t.health.repaired }
      : { title: t.edit.failed, body: answer.error, critical: true });
    check();
  };
  return (
    <PanelSection title={t.health.title}>
      {problems.map((p, i) => (
        <PanelSectionRow key={i}>
          <Field className="mh-qam-field" focusable highlightOnFocus padding="compact" bottomSeparator="none"
            label={<span className="mh-health"><FaExclamationTriangle aria-hidden="true" size={12} />
              {p.check === "launch-hooks" ? t.health.hooks : t.health.steamInput}</span>}
            description={p.message} />
        </PanelSectionRow>
      ))}
      {hooks && (
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={repair} disabled={repairing}>
            {repairing ? t.health.repairing : t.health.repair}
          </ButtonItem>
        </PanelSectionRow>
      )}
    </PanelSection>
  );
}
