import { callable } from "@decky/api";
import { useEffect, useState } from "react";
import type { Pad } from "../data";

// Steam's own pictures of each pad (its controller settings screen), read from the user's Steam install by the
// backend, never shipped. Each has the pixel size it was traced at and where each control sits on it:
// a circle [cx, cy, r] or a rounded box [cx, cy, w, h]. Shoulders and triggers can't be seen from the front; the
// drawing puts them in a strip above the picture instead.
// A circle [cx, cy, r], a rounded box [cx, cy, w, h], or a pill turned by `deg` degrees [cx, cy, w, h, deg]
// (the SNES's slanted Start and Select).
export type ArtSpot = [cx: number, cy: number, r: number] | [cx: number, cy: number, w: number, h: number]
  | [cx: number, cy: number, w: number, h: number, deg: number];

export interface Art {
  name: string; // the backend's name for the file
  width: number;
  height: number;
  spots: Record<string, ArtSpot>;
  blank?: boolean; // the buttons carry no markings: the drawing prints the pad's own glyphs on them
}

const XBOX: Art = {
  name: "xboxone", width: 1001, height: 703,
  spots: {
    face_north: [762, 128, 38], face_west: [690, 195, 38], face_east: [830, 195, 38], face_south: [762, 263, 38],
    ls: [245, 193, 76], rs: [635, 345, 76], dpad: [367, 355, 86],
    select: [428, 193, 26], start: [573, 193, 26], guide: [500, 93, 44],
  },
};

// Steam's picture for pads it knows only as a third-party type (an 8BitDo is type 50): offset sticks, View / Home /
// Menu in the middle, no maker's logo.
const GENERIC: Art = {
  name: "generic", width: 1005, height: 633, blank: true,
  spots: {
    face_north: [754, 127, 34], face_west: [698, 183, 34], face_east: [810, 183, 34], face_south: [754, 239, 34],
    ls: [249, 183, 80], rs: [635, 338, 80], dpad: [369, 338, 82],
    select: [423, 183, 25], start: [578, 183, 25], guide: [501, 182, 45],
  },
};

const DUALSENSE: Art = {
  name: "ps5", width: 1001, height: 678,
  spots: {
    face_north: [818, 112, 36], face_west: [751, 180, 36], face_east: [885, 180, 36], face_south: [818, 248, 36],
    ls: [338, 317, 72], rs: [664, 317, 72], dpad: [188, 178, 92],
    select: [268, 68, 22, 52], start: [732, 68, 22, 52], touchpad: [500, 110, 404, 206],
    guide: [502, 317, 34], misc1: [502, 374, 60, 18],
  },
};

const SWITCH_PRO: Art = {
  name: "switch_pro", width: 1000, height: 702,
  spots: {
    face_north: [763, 143, 39], face_west: [685, 211, 39], face_east: [841, 211, 39], face_south: [763, 275, 39],
    ls: [222, 210, 80], rs: [630, 348, 84], dpad: [346, 348, 76],
    select: [377, 134, 24], start: [623, 134, 24], guide: [569, 211, 27], misc1: [428, 211, 22],
  },
};

// The SVG is 449x181; traced on a 1000-wide render.
const DECK: Art = {
  name: "steam_deck", width: 1000, height: 403,
  spots: {
    face_north: [936, 42, 17], face_west: [907, 70, 17], face_east: [966, 70, 17], face_south: [936, 99, 17],
    ls: [154, 90, 32], rs: [841, 90, 32], dpad: [58, 73, 40],
    select: [117, 37, 40, 22], start: [881, 37, 40, 22], trackpad_l: [145, 201, 112, 112],
    trackpad_r: [851, 201, 112, 112], guide: [172, 286, 58, 26], qam: [824, 286, 58, 26],
  },
};

export function artFor(pad: Pick<Pad, "shape" | "family">): Art | null {
  if (pad.shape === "xbox") return pad.family?.startsWith("ms.") ? XBOX : GENERIC; // an 8BitDo isn't an Xbox pad
  if (pad.shape === "playstation" && pad.family === "sony.dualsense") return DUALSENSE;
  if (pad.shape === "nintendo") return SWITCH_PRO;
  if (pad.shape === "deck") return DECK;
  return null;
}

const getArt = callable<[string], { ok: boolean; data?: { url: string } }>("get_controller_art");
const cache = new Map<string, Promise<string | null>>();

function load(name: string): Promise<string | null> {
  let found = cache.get(name);
  if (!found) {
    found = getArt(name)
      .then((answer) => (answer?.ok && answer.data ? answer.data.url : null))
      .catch(() => null); // fixture builds, or an older Steam: the built-in drawing stays
    cache.set(name, found);
  }
  return found;
}

// The picture's data URL once loaded; null while loading or when Steam has none.
export function useArt(art: Art | null): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    setUrl(null);
    let live = true;
    if (art) load(art.name).then((u) => live && setUrl(u));
    return () => {
      live = false;
    };
  }, [art?.name]);
  return url;
}

// Fits the picture inside its box whichever way is tighter, keeping its shape, so the rings stay on their buttons.
export const fitStyle = (w: number, h: number) => ({
  aspectRatio: `${w} / ${h}`, width: `min(100cqw, calc(100cqh * ${(w / h).toFixed(4)}))`,
});
