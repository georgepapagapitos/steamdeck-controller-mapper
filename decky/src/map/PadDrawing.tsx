import type { CSSProperties } from "react";
import type { Pad, PadInput } from "../data";
import { Icon, glyphIcon, useSteamGlyphs } from "../glyphs";
import { t } from "../strings";
import { type Control, controlKind, controlTargets } from "./controls";
import { type Art, type ArtSpot, artFor, fitStyle, useArt } from "./art";
import { steamKey } from "./BackStrip";
import { BOX, type Spot, shapeDef } from "./shapes";

interface Props {
  pad: Pad;
  controls: Control[];
  selected: string | null;
  outlined?: string | null; // waiting for a press: the control that does the job now, ringed but not lit
  extras?: PadInput[]; // the inputs only Steam sees (paddles, back and extra bumpers), keyed steam:<input>
}

// Box units → percentages of the drawing, and font sizes in container-width units, so the drawing scales with
// its column and the labels stay on their buttons.
const pctX = (n: number) => `${(n / BOX.width) * 100}%`;
const pctY = (n: number) => `${(n / BOX.height) * 100}%`;
const cq = (n: number) => `${(n / BOX.width) * 100}cqw`;

function spotStyle([cx, cy, w, h]: Spot, glyph: string): CSSProperties {
  return {
    left: pctX(cx - w / 2),
    top: pctY(cy - h / 2),
    width: pctX(w),
    height: pctY(h),
    borderRadius: cq(Math.min(w, h) / 2),
    fontSize: cq(glyph.length > 2 ? 12 : 16),
  };
}

// Kenney's glyphs fill about 3/4 of their box (8-56 of 64), so a glyph's box is 4/3 of the spot it stands for;
// wide, short spots (shoulders, Select/Start) take their size from the width.
function iconStyle([cx, cy, w, h]: Spot): CSSProperties {
  const size = (Math.max(Math.min(w, h), 0.6 * Math.max(w, h)) * 4) / 3;
  return { left: pctX(cx - size / 2), top: pctY(cy - size / 2), width: pctX(size), height: pctY(size) };
}

export function spotLabel(control: Control, prefix: string): string {
  const targets = controlTargets(control);
  const what = targets.length ? targets.map((l) => (prefix ? `${prefix} ${l}` : l)).join(", ") : t.map.nothing;
  return `${control.glyph}, ${control.name}: ${what}`;
}

// The pad in its own shape, each control labelled with the pad's glyph and coloured by where its mapping comes
// from. It's a picture, not something to navigate: Steam's D-pad focus can't move reliably between freely placed
// buttons, so the list beside it takes focus and the drawing lights up whichever control the list is on.
// A control with a Kenney glyph is drawn as that glyph, tinted with its source's colour; any other keeps its label
// in a bordered pill, the border in that colour.
export function PadDrawing({ pad, controls, selected, outlined, extras }: Props) {
  useSteamGlyphs();
  const art = artFor(pad);
  const url = useArt(art);
  if (art && url) {
    return <ArtDrawing pad={pad} art={art} url={url} controls={controls} selected={selected} outlined={outlined} extras={extras} />;
  }
  const def = shapeDef(pad.shape);
  const placed = controls.filter((c) => def.spots[c.key]);
  return (
    <div className="mh-pad" role="img" aria-label={t.map.drawing(pad.name)}>
      <svg viewBox={`0 0 ${BOX.width} ${BOX.height}`} aria-hidden="true">
        {def.outline}
      </svg>
      {placed.map((control) => {
        const icon = glyphIcon(pad, control.glyph);
        const spot = def.spots[control.key];
        return (
          <div
            key={control.key}
            className={`mh-spot${icon ? " mh-spot-icon" : ""}${control.key === selected && !outlined ? " mh-on" : ""}${
              control.key === outlined ? " mh-was" : ""}`}
            data-kind={controlKind(control)}
            style={icon ? iconStyle(spot) : spotStyle(spot, control.glyph)}
            aria-hidden="true"
          >
            {icon ? <Icon name={icon} size="100%" /> : control.glyph}
          </div>
        );
      })}
    </div>
  );
}

const SHOULDERS_LEFT = ["l2", "l1"];
const SHOULDERS_RIGHT = ["r1", "r2"];

function ringStyle(art: Art, spot: ArtSpot): CSSProperties {
  const [cx, cy, a, b] = spot;
  const w = b === undefined ? a * 2 : a;
  const h = b === undefined ? a * 2 : b;
  return {
    left: `${((cx - w / 2) / art.width) * 100}%`, top: `${((cy - h / 2) / art.height) * 100}%`,
    width: `${(w / art.width) * 100}%`, height: `${(h / art.height) * 100}%`,
    borderRadius: b === undefined ? "50%" : `${(Math.min(w, h) / 2 / art.width) * 100}cqw`,
  };
}

// Steam's picture of the pad, with the control the list is on ringed in place. Shoulders and triggers sit in a strip
// above it, where they are on the pad. Nothing else is drawn on the picture: what each button does is in the list.
// An 8BitDo Ultimate's L4/R4 sit on top beside the bumpers; every other Steam-only button (its PL/PR, the Deck's
// L4/L5/R4/R5, an Edge's paddles) is on the back.
const onTop = (pad: Pad, input: PadInput) => !!pad.family?.startsWith("8bitdo") && (input.glyph === "L4" || input.glyph === "R4");
const isLeft = (input: PadInput) => input.glyph.startsWith("L") || input.glyph === "PL";

function ArtDrawing({ pad, art, url, controls, selected, outlined, extras = [] }: Props & { art: Art; url: string }) {
  const lit = outlined ?? selected;
  const chip = (key: string, glyph: string, kind: string) => {
    const icon = glyphIcon(pad, glyph);
    const on = key === lit;
    return (
      <div key={key} className={`mh-shoulder${on ? (outlined ? " mh-was" : " mh-on") : ""}`} data-kind={kind}>
        {icon ? <Icon name={icon} size={26} /> : glyph}
      </div>
    );
  };
  const shoulder = (key: string) => {
    const control = controls.find((c) => c.key === key);
    return control ? chip(key, control.glyph, controlKind(control)) : null;
  };
  const extra = (input: PadInput) => chip(steamKey(input), input.glyph, "steam");
  const back = extras.filter((i) => !art.spots[i.input] && !onTop(pad, i));
  const top = extras.filter((i) => onTop(pad, i));
  const ring = lit ? art.spots[lit] : undefined;
  return (
    <div className="mh-art-wrap" role="img" aria-label={t.map.drawing(pad.name)}>
      <div className="mh-shoulders" aria-hidden="true">
        <div>{SHOULDERS_LEFT.map(shoulder)}{top.filter(isLeft).map(extra)}</div>
        <div>{top.filter((i) => !isLeft(i)).map(extra)}{SHOULDERS_RIGHT.map(shoulder)}</div>
      </div>
      <div className="mh-art-box">
      <div className="mh-art" style={fitStyle(art.width, art.height)} aria-hidden="true">
        <img src={url} alt="" />
        {art.blank && controls.map((c) => {
          const spot = art.spots[c.key];
          const icon = spot && c.key !== "ls" && c.key !== "rs" && c.key !== "dpad" ? glyphIcon(pad, c.glyph) : null;
          return icon && <div key={c.key} className="mh-art-glyph" style={ringStyle(art, spot)}><Icon name={icon} size="62%" /></div>;
        })}
        {ring && <div className={`mh-ring${outlined ? " mh-ring-was" : ""}`} style={ringStyle(art, ring)} />}
      </div>
      </div>
      {back.length > 0 && (
        <div className="mh-shoulders mh-backs" aria-hidden="true">
          <div>{back.filter(isLeft).map(extra)}</div>
          <span className="mh-backs-label">{t.map.back_}</span>
          <div>{back.filter((i) => !isLeft(i)).map(extra)}</div>
        </div>
      )}
    </div>
  );
}
