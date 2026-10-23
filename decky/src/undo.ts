import { toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { t } from "./strings";

// The last change made from the plugin, undone with Y on the button map or from its ≡ menu (docs/08 principle 4:
// undo is one press away). One step: a new change replaces it. Kept while the plugin is loaded.
export interface Undoable {
  label: string; // "N64 A on Y, this game"
  run: () => Promise<string | null>; // null when undone, else why it couldn't be
}

let last: Undoable | null = null;
const listeners = new Set<(u: Undoable | null) => void>();

export function setUndo(undo: Undoable | null) {
  last = undo;
  for (const listener of listeners) listener(last);
}

export async function undoLast(): Promise<boolean> {
  const undo = last;
  if (!undo) return false;
  setUndo(null);
  const error = await undo.run();
  toaster.toast(error ? { title: t.edit.failed, body: error, critical: true } : { title: t.title, body: t.edit.undone });
  return !error;
}

export function useUndo(): Undoable | null {
  const [undo, set] = useState(last);
  useEffect(() => {
    listeners.add(set);
    return () => {
      listeners.delete(set);
    };
  }, []);
  return undo;
}
