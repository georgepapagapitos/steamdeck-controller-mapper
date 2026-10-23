import type { Launch, LastLaunch, PadOption, Policy, Source } from "./data";
import { t } from "./strings";

// "Legend of Zelda, The - Ocarina of Time (USA) (Rev 2)" → "The Legend of Zelda: Ocarina of Time".
// No-Intro style names: drop the (region) and [flag] tags, move a trailing ", The" to the front.
export function gameTitle(launch: Launch): string {
  const raw = launch.game?.trim();
  if (!raw) return t.unknownGame;
  let name = raw.replace(/\s*[([][^)\]]*[)\]]/g, "").trim();
  name = name.replace(/^(.+?), (The|A|An)\b/, "$2 $1");
  name = name.replace(/ - /g, ": ");
  return name || raw;
}

// The part after the colon is what people call it ("Ocarina of Time"); fall back to the whole title.
export function shortGameTitle(launch: Launch): string {
  const full = gameTitle(launch);
  const parts = full.split(": ");
  return parts.length > 1 ? parts.slice(1).join(": ") : full;
}

const PROGRAM_NAMES: Record<string, string> = {
  retroarch: "RetroArch",
  dolphin: "Dolphin",
  duckstation: "DuckStation",
  pcsx2: "PCSX2",
  ppsspp: "PPSSPP",
  cemu: "Cemu",
  ryujinx: "Ryujinx",
  rpcs3: "RPCS3",
  xemu: "xemu",
  melonds: "melonDS",
  mupen64plus_next: "Mupen64Plus-Next",
  parallel_n64: "ParaLLEl N64",
  snes9x: "Snes9x",
  bsnes: "bsnes",
  mesen: "Mesen",
  nestopia: "Nestopia",
  genesis_plus_gx: "Genesis Plus GX",
  mgba: "mGBA",
  gambatte: "Gambatte",
  swanstation: "SwanStation",
  beetle_psx_hw: "Beetle PSX HW",
  flycast: "Flycast",
};

export function programName(id: string | null | undefined): string {
  if (!id) return "";
  return PROGRAM_NAMES[id] ?? id;
}

// "Nintendo 64 · RetroArch · Mupen64Plus-Next"
export function launchLine(launch: Launch): string {
  return [launch.system_name || launch.system.toUpperCase(), programName(launch.emulator), programName(launch.core)]
    .filter(Boolean)
    .join(" · ");
}

// Short console prefix for target labels: "N64 C▼". Long system ids read badly as a prefix, so they get none.
export function systemPrefix(launch: Launch): string {
  return launch.system.length <= 4 ? launch.system.toUpperCase() : "";
}

export function outcomeText(launch: Launch): string {
  return t.outcome[launch.outcome] ?? t.outcomeUnknown(launch.outcome);
}

export function policyText(policy: Policy | null | undefined, mode: string): string {
  if (!policy) return t.policy["steam-order"];
  if (policy.name === "steam-order" && mode === "es-de") return t.policy["steam-order-es-de"];
  return t.policy[policy.name] ?? t.policyUnknown(policy.name);
}

// "Today, 10:55" / "Yesterday, 22:10" / "Oct 20, 14:02". `ts` is local time without a zone.
export function launchTime(ts: string, now: Date = new Date()): string {
  const when = new Date(ts);
  if (Number.isNaN(when.getTime())) return ts;
  const time = when.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  const day = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const thatDay = new Date(when.getFullYear(), when.getMonth(), when.getDate()).getTime();
  const days = Math.round((day - thatDay) / 86400000);
  if (days === 0) return `${t.today}, ${time}`;
  if (days === 1) return `${t.yesterday}, ${time}`;
  return `${when.toLocaleDateString(undefined, { month: "short", day: "numeric" })}, ${time}`;
}

export function modeName(mode: string): string {
  return t.modes[mode] ?? mode;
}

export function sourceKindName(source: Source | undefined): string {
  return t.source[source?.kind ?? ""] ?? t.source.unknown;
}

// "Your rule · N64 layout 1: … · all N64 games, any pad" / "Emulator default · Mupen64Plus-Next default"
export function sourceWords(source: Source | undefined): string {
  if (!source) return t.source.unknown;
  const parts = [sourceKindName(source)];
  if (source.kind === "rule") {
    if (source.rule_label) parts.push(source.rule_label);
    else if (source.rule_id) parts.push(source.rule_id);
    if (source.scope) parts.push(source.scope);
  } else if (source.detail) {
    parts.push(source.detail);
  }
  return parts.join(" · ");
}

// The value to show next to an option's label, or "" when the label already says it ("Rumble pak").
export function optionValue(option: PadOption): string {
  const { value, key, label } = option;
  if (value === null || value === undefined) return "";
  if (typeof value === "boolean") return value ? t.options.on : t.options.off;
  if (typeof value === "number") {
    return key.includes("deadzone") && value >= 0 && value <= 1 ? t.options.percent(value) : String(value);
  }
  return label.toLowerCase().includes(value.toLowerCase()) ? "" : value;
}

export function optionText(option: PadOption): string {
  const value = optionValue(option);
  return value ? `${option.label} ${value}` : option.label;
}

export function warningText(warning: unknown): string {
  if (typeof warning === "string") return warning;
  if (warning && typeof warning === "object" && "message" in warning) return String(warning.message);
  return JSON.stringify(warning);
}

export function hasPlayers(data: LastLaunch): boolean {
  return Array.isArray(data.players) && data.players.length > 0;
}

// "8Bitdo Ultimate 2 Wireless Controller" → "8BitDo Ultimate 2", "Steam Deck Controller" → "Steam Deck": tabs
// and rows are narrow, and "Wireless Controller" says nothing there.
export function shortPadName(name: string): string {
  const short = name
    .replace(/^8bitdo\b/i, "8BitDo")
    .replace(/\s+(Wireless\s+)?Controller$/i, "")
    .trim();
  return short || name;
}

// A canonical physical input (docs/03) in positional words, for a rule that applies to any pad.
const POSITIONS: Record<string, string> = {
  face_south: "the bottom face button", face_east: "the right face button", face_west: "the left face button",
  face_north: "the top face button", dpad_up: "D-pad up", dpad_down: "D-pad down", dpad_left: "D-pad left",
  dpad_right: "D-pad right", l1: "the left bumper", r1: "the right bumper", l2: "the left trigger",
  r2: "the right trigger", l3: "the left stick click", r3: "the right stick click", ls_x: "the left stick",
  ls_y: "the left stick", rs_x: "the right stick", rs_y: "the right stick", select: "Select", start: "Start",
  guide: "the guide button", misc1: "the extra button", touchpad_click: "the touchpad click", none: "nothing",
};

export function positionWords(input: string): string {
  const half = input.match(/^(ls|rs)_(up|down|left|right)$/);
  if (half) return `on the ${half[1] === "ls" ? "left" : "right"} stick ${half[2]}`;
  const words = POSITIONS[input];
  return words ? (input === "none" ? "off" : `on ${words}`) : `on ${input.replace(/\+/g, " + ")}`;
}
