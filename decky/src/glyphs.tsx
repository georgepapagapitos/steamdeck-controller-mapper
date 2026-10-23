import icons from "mh:kenney";
import type { CSSProperties } from "react";
import type { Pad } from "./data";

// Pad glyphs and controller icons from Kenney's Input Prompts (CC0, assets/kenney/License.txt). An icon is picked
// by the drawing family (the pad's shape) and the label the core sends, which is what's printed on the pad
// (data/glyphs.json): a label with no icon here (an 8BitDo's PL, a Switch pad's Capture) stays text. So a family
// that relabels a button never gets another pad's icon.
type Table = Record<string, string>;

const PLAYSTATION: Table = {
  "✕": "playstation_button_cross", "○": "playstation_button_circle", "□": "playstation_button_square",
  "△": "playstation_button_triangle", "D-pad": "playstation_dpad",
  L1: "playstation_trigger_l1", R1: "playstation_trigger_r1", L2: "playstation_trigger_l2", R2: "playstation_trigger_r2",
  LS: "playstation_stick_l", RS: "playstation_stick_r", L3: "playstation_button_l3", R3: "playstation_button_r3",
  Share: "playstation4_button_share", Options: "playstation4_button_options", Touchpad: "playstation4_touchpad",
};

// The DualSense's own: Create, Options and the touchpad are drawn differently from a DualShock 4's.
const DUALSENSE: Table = {
  ...PLAYSTATION, Create: "playstation5_button_create", Options: "playstation5_button_options",
  Mic: "playstation5_button_mute", Touchpad: "playstation5_touchpad",
};

const XBOX: Table = {
  A: "xbox_button_a", B: "xbox_button_b", X: "xbox_button_x", Y: "xbox_button_y", "D-pad": "xbox_dpad",
  LB: "xbox_lb", RB: "xbox_rb", LT: "xbox_lt", RT: "xbox_rt",
  LS: "xbox_stick_l", RS: "xbox_stick_r", L3: "xbox_stick_l_press", R3: "xbox_stick_r_press",
  View: "xbox_button_view", Menu: "xbox_button_menu", Xbox: "xbox_guide", Share: "xbox_button_share",
  // Elite paddles as SDL numbers them (data/glyphs.json): P1 upper right, P3 upper left, P2 lower right, P4 lower left.
  P1: "xbox_elite_paddle_top_right", P3: "xbox_elite_paddle_top_left",
  P2: "xbox_elite_paddle_bottom_right", P4: "xbox_elite_paddle_bottom_left",
};

const NINTENDO: Table = {
  A: "switch_button_a", B: "switch_button_b", X: "switch_button_x", Y: "switch_button_y", "D-pad": "switch_dpad",
  L: "switch_button_l", R: "switch_button_r", ZL: "switch_button_zl", ZR: "switch_button_zr",
  LS: "switch_stick_l", RS: "switch_stick_r", L3: "switch_stick_l_press", R3: "switch_stick_r_press",
  "−": "switch_button_minus", "+": "switch_button_plus", Home: "switch_button_home",
};

const DECK: Table = {
  A: "steamdeck_button_a", B: "steamdeck_button_b", X: "steamdeck_button_x", Y: "steamdeck_button_y",
  "D-pad": "steamdeck_dpad", L1: "steamdeck_button_l1", R1: "steamdeck_button_r1", L2: "steamdeck_button_l2",
  R2: "steamdeck_button_r2", LS: "steamdeck_stick_l", RS: "steamdeck_stick_r", L3: "steamdeck_stick_l_press",
  R3: "steamdeck_stick_r_press", View: "steamdeck_button_view", Menu: "steamdeck_button_options",
  Steam: "steamdeck_button_guide", L4: "steamdeck_button_l4", L5: "steamdeck_button_l5", R4: "steamdeck_button_r4",
  R5: "steamdeck_button_r5", "L pad": "steamdeck_trackpad_l", "R pad": "steamdeck_trackpad_r",
};

type PadLike = Pick<Pad, "shape"> & { family?: string | null };

function table(pad: PadLike): Table | null {
  if (pad.shape === "playstation") return pad.family === "sony.dualsense" ? DUALSENSE : PLAYSTATION;
  if (pad.shape === "xbox") return XBOX;
  if (pad.shape === "nintendo") return NINTENDO;
  if (pad.shape === "deck") return DECK;
  return null;
}

export function glyphIcon(pad: PadLike, label: string): string | null {
  const name = table(pad)?.[label];
  return name && icons[name] ? name : null;
}

export function padIcon(pad: PadLike): string | null {
  const name =
    pad.family === "sony.dualshock4" ? "controller_playstation4"
    : pad.shape === "playstation" ? "controller_playstation5"
    : pad.family === "ms.xbox360" ? "controller_xbox360"
    : pad.shape === "xbox" ? "controller_xboxseries"
    : pad.shape === "nintendo" ? "controller_switch_pro"
    : pad.shape === "deck" ? "controller_steamdeck"
    : null;
  return name && icons[name] ? name : null;
}

const urls = new Map<string, string>();

function maskUrl(name: string): string {
  let url = urls.get(name);
  if (!url) {
    url = `url("data:image/svg+xml;charset=utf-8,${encodeURIComponent(icons[name])}")`;
    urls.set(name, url);
  }
  return url;
}

// An icon drawn in the current text colour (a CSS mask over currentColor), so it takes the colour of its source
// like the text around it. Decorative: the caller says what it is in words.
export function Icon({ name, size, className }: { name: string; size: number | string; className?: string }) {
  const url = maskUrl(name);
  const style: CSSProperties = {
    width: size, height: size, flex: "none", display: "inline-block", backgroundColor: "currentColor",
    WebkitMaskImage: url, maskImage: url, WebkitMaskSize: "contain", maskSize: "contain",
    WebkitMaskRepeat: "no-repeat", maskRepeat: "no-repeat", WebkitMaskPosition: "center", maskPosition: "center",
  };
  return <span className={className} style={style} aria-hidden="true" />;
}

// A pad's own label as its icon when there is one, else as text.
export function Glyph({ pad, label, size, className }: {
  pad: PadLike;
  label: string;
  size: number | string;
  className?: string;
}) {
  const name = glyphIcon(pad, label);
  return name ? <Icon name={name} size={size} className={className} /> : <span className={className}>{label}</span>;
}
