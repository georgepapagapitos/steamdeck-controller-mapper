import { callable } from "@decky/api";
import { useCallback, useEffect, useRef, useState } from "react";
import fixture from "mh:fixture";
import type { LastLaunchResult } from "./data";
import { t } from "./strings";

const getLastLaunchRpc = callable<[], LastLaunchResult>("get_last_launch");

// The backend never raises, but the call itself can fail (plugin stopped, loader restarting).
async function getLastLaunch(): Promise<LastLaunchResult> {
  if (fixture) return fixture;
  try {
    const result = await getLastLaunchRpc();
    if (result && typeof result === "object" && "ok" in result) return result;
    return { ok: false, code: "bad-output", error: t.errors.badAnswer };
  } catch (e) {
    console.error("map-helper: get_last_launch failed", e);
    return { ok: false, code: "failed", error: t.errors.noBackend };
  }
}

export type LastLaunchState = { status: "loading" } | { status: "done"; result: LastLaunchResult };

// Which pads Steam has now, as "index:type" pairs: Steam's ControllerStore global (the client of 2026-10-23 has no
// controller-list event in SteamClient.Input). Compared in place; nothing about a pad leaves the page.
function padsNow(): string {
  try {
    const store = (window as unknown as { ControllerStore?: { GetControllers(): { nControllerIndex: number; eControllerType: number }[] } })
      .ControllerStore;
    return (store?.GetControllers() ?? []).map((c) => `${c.nControllerIndex}:${c.eControllerType}`).sort().join(",");
  } catch {
    return "";
  }
}

const PADS_POLL_MS = 1000;
const PADS_SETTLE_MS = 1200; // after a pad comes or goes, Steam seats it and the kernel lists it before we ask

// Fetches on mount, on reload(), and when a pad connects or disconnects (the answer is the last launch's game with
// the pads connected now). Keeps showing the previous answer while a reload is running.
export function useLastLaunch() {
  const [state, setState] = useState<LastLaunchState>({ status: "loading" });
  const [reloading, setReloading] = useState(false);
  const live = useRef(true);
  const request = useRef(0);

  const reload = useCallback(async () => {
    const id = ++request.current;
    setReloading(true);
    const result = await getLastLaunch();
    if (!live.current || id !== request.current) return;
    setState({ status: "done", result });
    setReloading(false);
  }, []);

  useEffect(() => {
    live.current = true;
    reload();
    if (fixture) return () => {
      live.current = false;
    };
    let pads = padsNow();
    let settle: ReturnType<typeof setTimeout> | null = null;
    const poll = setInterval(() => {
      const now = padsNow();
      if (now === pads) return;
      pads = now;
      if (settle) clearTimeout(settle);
      settle = setTimeout(reload, PADS_SETTLE_MS);
    }, PADS_POLL_MS);
    return () => {
      live.current = false;
      clearInterval(poll);
      if (settle) clearTimeout(settle);
    };
  }, [reload]);

  return { state, reloading, reload };
}
