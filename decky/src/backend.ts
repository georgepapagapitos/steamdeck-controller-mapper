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

// Fetches on mount and on reload(). Keeps showing the previous answer while a reload is running.
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
    return () => {
      live.current = false;
    };
  }, [reload]);

  return { state, reloading, reload };
}
