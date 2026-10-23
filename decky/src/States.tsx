import { SteamSpinner } from "@decky/ui";
import type { LastLaunchResult } from "./data";
import { t } from "./strings";

type Failure = Extract<LastLaunchResult, { ok: false }>;

// Title and body for an answer that isn't a launch. Two of them are normal states, not errors.
export function failureText(result: Failure): { title: string; body: string; expected: boolean } {
  if (result.code === "not-installed") {
    return { title: t.states.notInstalledTitle, body: t.states.notInstalledBody, expected: true };
  }
  if (result.code === "no-launch") {
    return { title: t.states.noLaunchTitle, body: t.states.noLaunchBody, expected: true };
  }
  return { title: t.states.errorTitle, body: result.error, expected: false };
}

export function Loading() {
  return (
    <div className="mh-state" role="status">
      <SteamSpinner background="transparent" style={{ height: 48 }} />
      <div className="mh-state-body">{t.loading}</div>
    </div>
  );
}

export function Message({ title, body }: { title: string; body: string }) {
  return (
    <div className="mh-state" role="status">
      <div className="mh-state-title">{title}</div>
      <div className="mh-state-body">{body}</div>
    </div>
  );
}

export function SampleBanner({ result }: { result: LastLaunchResult }) {
  return result.sample ? <div className="mh-sample">{t.sample}</div> : null;
}
