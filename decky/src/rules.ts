import { callable } from "@decky/api";
import fixture from "mh:fixture";
import { t } from "./strings";

// The backend's rule calls (main.py), which run `map-helper rules` (core/maphelper/rules.py). Shapes are the core's.

export interface Scope {
  controller:
    | { level: "any" }
    | { level: "family" | "model" | "brand" | "style"; value: string }
    | { level: "device"; player: number; model?: string | null };
  content: { level: "system"; system: string } | { level: "game"; system: string; game_id: string };
}

export type Op =
  | { op: "set"; target: string; source: { input: string }; rule?: string; scope?: Scope }
  | { op: "unset"; target: string; rule: string };

// One input whose job changes, for one player of the pads connected now.
export interface Change {
  player: number;
  pad: string;
  input: string;
  glyph: string;
  name: string;
  before: string[];
  after: string[];
}

export interface EditResult {
  rules: string[];
  undo: Op[];
  changes: Change[] | null; // null when there was no last launch to preview against (preview_error says why)
  preview_error: string | null;
  dry_run: boolean;
}

export interface RuleRow {
  id: string;
  label: string;
  on: boolean;
  parked: boolean; // in rules-off/
  edit: boolean; // made by the button map ("Button map changes")
  file: string;
  system: string | null;
  system_name: string | null;
  content_level: string;
  game: string | null;
  controller_level: string;
  scope: string;
  bindings: { target: string; label: string; input: string }[];
  options: number;
  notes: string;
  clashes: string[];
}

export interface Target {
  target: string;
  label: string;
  kind: "button" | "dpad" | "axis";
}

export type Answer<T> = { ok: true; data: T } | { ok: false; code: string; error: string };

async function ask<T>(method: string, ...args: unknown[]): Promise<Answer<T>> {
  try {
    const answer = await callable<unknown[], Answer<T>>(method)(...args);
    if (answer && typeof answer === "object" && "ok" in answer) return answer;
    return { ok: false, code: "bad-output", error: t.errors.badAnswer };
  } catch (e) {
    console.error(`map-helper: ${method} failed`, e);
    return { ok: false, code: "failed", error: t.errors.noBackend };
  }
}

// A fixture build shows sample data, so it never changes the real rules: edits only preview, the rest refuse.
const sampleOnly = <T>(): Answer<T> => ({ ok: false, code: "sample", error: t.rules.sampleOnly });

export const getRules = () => ask<{ rules: RuleRow[]; problems: { file: string; problem: string }[] }>("get_rules");
export const getTargets = (system: string) => ask<{ targets: Target[] }>("get_targets", system);
export const editRules = (ops: Op[], dryRun = false) => ask<EditResult>("edit_rules", ops, dryRun || !!fixture);
export const setRulesOn = (ids: string[], on: boolean) =>
  fixture ? Promise.resolve(sampleOnly<{ warnings: string[] }>()) : ask<{ warnings: string[] }>("set_rules_on", ids, on);
export const deleteRules = (ids: string[]) =>
  fixture ? Promise.resolve(sampleOnly<{ rules: string[] }>()) : ask<{ rules: string[] }>("delete_rules", ids);
export const resetRules = (system: string, game: string | null, dryRun: boolean) =>
  ask<{ rules: string[]; labels: string[]; dry_run: boolean }>("reset_rules", system, game, dryRun || !!fixture);
export const getSystemLogo = (system: string) => ask<{ url: string }>("get_system_logo", system);

// Changes saved since the button map's data was recorded: they apply at the next launch, so the map, which shows
// what the last launch got, says so until then. Kept while the plugin is loaded; reset when a new launch shows up.
let pending: { ts: string; count: number } | null = null;

export function notePending(launchTs: string, count: number) {
  pending = { ts: launchTs, count: Math.max(0, (pending?.ts === launchTs ? pending.count : 0) + count) };
}

export function pendingFor(launchTs: string): number {
  return pending?.ts === launchTs ? pending.count : 0;
}
