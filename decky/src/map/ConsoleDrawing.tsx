import { callable } from "@decky/api";
import { type CSSProperties, useEffect, useState } from "react";
import { type ArtSpot, fitStyle } from "./art";

// A real photo of the emulated console's controller (public domain, Wikimedia Commons, shipped in
// assets/consoles with the spots traced on it), with the buttons the selected control becomes ringed in place.
// Buttons the photo can't show (shoulders, triggers, Z) sit as chips above it.
interface ConsoleArt {
  url: string;
  width: number;
  height: number;
  spots: Record<string, ArtSpot>;
  hidden?: string[];
  edge?: Record<string, number>; // a hidden button's x on the top edge, as a fraction of the width (traced)
  background?: string;
}

const getConsoleArt = callable<[string, string], { ok: boolean; data?: ConsoleArt }>("get_console_art");
const cache = new Map<string, Promise<ConsoleArt | null>>();

function load(system: string, controller: string): Promise<ConsoleArt | null> {
  const key = `${system}/${controller}`;
  let found = cache.get(key);
  if (!found) {
    found = getConsoleArt(system, controller)
      .then((answer) => (answer?.ok && answer.data ? answer.data : null))
      .catch(() => null);
    cache.set(key, found);
  }
  return found;
}

function useConsoleArt(system: string, controller: string | null): ConsoleArt | null {
  const [art, setArt] = useState<ConsoleArt | null>(null);
  useEffect(() => {
    setArt(null);
    let live = true;
    if (controller) load(system, controller).then((a) => live && setArt(a));
    return () => {
      live = false;
    };
  }, [system, controller]);
  return art;
}

function ringStyle(art: ConsoleArt, [cx, cy, a, b, deg]: ArtSpot): CSSProperties {
  const w = b === undefined ? a * 2 : a;
  const h = b === undefined ? a * 2 : b;
  return {
    left: `${((cx - w / 2) / art.width) * 100}%`, top: `${((cy - h / 2) / art.height) * 100}%`,
    width: `${(w / art.width) * 100}%`, height: `${(h / art.height) * 100}%`,
    borderRadius: b === undefined ? "50%" : deg !== undefined ? "999px" : "18%",
    ...(deg !== undefined ? { transform: `rotate(${deg}deg)` } : {}),
  };
}

const DIRECTIONS = ["up", "down", "left", "right"];

// A target's spot: its own name, else its stick's (stick_x -> stick, main_y -> main, gc c_x -> c, l3 -> lstick).
function spotName(art: ConsoleArt, name: string): string {
  if (art.spots[name] || (art.hidden ?? []).includes(name)) return name;
  const stick = name.replace(/_[xy]$/, "");
  if (stick !== name && art.spots[stick]) return stick;
  const press = { l3: "lstick", r3: "rstick" }[name];
  if (press && art.spots[press]) return press;
  return name;
}

// The spots to ring for these button names: all four d-pad arms read as the whole d-pad.
function lit(art: ConsoleArt, names: string[]): string[] {
  const set = new Set(names.map((n) => spotName(art, n)));
  if (DIRECTIONS.every((d) => set.has(d)) && art.spots.dpad) {
    DIRECTIONS.forEach((d) => set.delete(d));
    set.add("dpad");
  }
  return [...set];
}

// Buttons the photo can't show (shoulders, triggers, Z) sit on the photo's top edge over where they are: left ones
// over the left shoulder from the outside in (L2 then L1), right ones mirrored, the rest in the middle.
const side = (name: string): "left" | "right" | "middle" =>
  /^(l|z?l)(\d|_|$)|^zl|^l_/.test(name) ? "left" : /^(r|z?r)(\d|_|$)|^zr|^r_/.test(name) ? "right" : "middle";
const outward = (name: string) => (/2|analog|trigger|^z/.test(name) ? 0 : 1); // triggers and Z sit outside the bumpers

function placeHidden(hidden: string[], edge: Record<string, number> | null | undefined): [string, number][] {
  edge ??= {};
  const at = edge;
  const out: [string, number][] = hidden.filter((h) => at[h] !== undefined).map((h) => [h, at[h] * 100]);
  hidden = hidden.filter((h) => at[h] === undefined);
  const left = hidden.filter((h) => side(h) === "left").sort((a, b) => outward(a) - outward(b));
  const right = hidden.filter((h) => side(h) === "right").sort((a, b) => outward(a) - outward(b));
  const middle = hidden.filter((h) => side(h) === "middle");
  left.forEach((h, i) => out.push([h, 16 + i * 12]));
  right.forEach((h, i) => out.push([h, 84 - i * 12]));
  middle.forEach((h, i) => out.push([h, 50 + (i - (middle.length - 1) / 2) * 12]));
  return out;
}

const chipLabel = (name: string, labels: Record<string, string>) =>
  labels[name] ?? name.replace(/_digital$/, "").replace(/_/g, " ").toUpperCase();

export function ConsoleDrawing({ system, controller, targets, labels, name }: {
  system: string;
  controller: string | null; // the layout's controller key, from the drives' targets ("n64.standard.a")
  targets: string[]; // button names the selected control becomes: ["a"], ["up", "down", "left", "right"]
  labels: Record<string, string>; // button name -> the console's own label, for the chips
  name: string; // "Game Boy Advance", for screen readers
}) {
  const art = useConsoleArt(system, controller);
  if (!art) return null;
  const on = lit(art, targets);
  const hidden = art.hidden ?? [];  // null-safe: the backend sends null for a missing key
  return (
    <div className="mh-art-wrap" role="img" aria-label={name}>
      <div className={`mh-art-box${hidden.length ? " mh-console-box" : ""}`}>
        <div className={`mh-art mh-console${art.background && art.background !== "transparent" ? " mh-console-boxed" : ""}`}
          style={fitStyle(art.width, art.height)} aria-hidden="true">
          <img src={art.url} alt="" />
          {on.map((n) => art.spots[n] && <div key={n} className="mh-ring" style={ringStyle(art, art.spots[n])} />)}
          {placeHidden(hidden, art.edge).map(([h, x]) => (
            <div key={h} className={`mh-shoulder mh-edge${on.includes(h) ? " mh-on" : ""}`} style={{ left: `${x}%` }}>
              {chipLabel(h, labels)}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

