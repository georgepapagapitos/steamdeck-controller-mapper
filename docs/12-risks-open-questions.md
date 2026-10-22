# 12 — Risks & Open Questions

## Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| R1 | **Player slot ↔ emulator device index mismatch** (Steam virtual pad order ≠ our probe order) | High | High: wrong mapping on the wrong player | Spike #1. Fall back to `steam-order`, show the active slot order in the UI, and add a "swap P1/P2" quick action |
| R2 | Steam grabs evdev, which breaks press-to-bind capture | Medium | Medium | hidraw capture; capture via Steam virtual pad; list-mode fallback |
| R3 | Capture input also navigates the Steam UI | High | Medium | Focus trap + hold-to-confirm; drive the UI from a second controller |
| R4 | EmuDeck changes launchers/structure → hooks break | Medium | High: silently stops applying | Hook health check on plugin load; `doctor`; upstream hook (Option C) |
| R5 | Emulator config formats change between versions | High (over time) | Medium | Version-keyed naming tables; fixtures per version; adapter refuses to write when the version is unknown + format mismatch (fail-open) |
| R6 | Corrupting a user's config | Low | Very high | Round-trip parsers, managed keys only, atomic writes, pristine backups, refuse while the emulator is running |
| R7 | Launch delay | Low | Medium | 500 ms budget, no-op skip, caching (controller DB index, adapter detection) |
| R8 | Double remapping (Steam layout + ours) confuses users | Medium | Medium | Guidance copy; stretch: detect non-passthrough Steam layouts |
| R9 | Ambiguous controller identity (8BitDo X/S modes, dongles) | High | Low–Medium | User claims; identity linking; clear UI |
| R10 | Decky API changes | Medium | Medium | Thin UI layer; core is independent of Decky |
| R11 | Scope explosion (20+ emulators) | High | High | Strict P0/P1 tiers; adapter template; community contributions |
| R12 | Perceived overlap with EmuDeck / SRM | Medium | Low | Position as complementary; pursue upstream collaboration early |
| R13 | Game id unavailable for compressed ROMs | High | Low | Multiple id sources; game rules degrade gracefully |
| R14 | **EmuDeck AutoMap** rewrites Dolphin (and Cemu / Switch emulator) input at every launch, after our wrapper | High (on by default) | High: our Dolphin writes are silently undone | Setup turns AutoMap off for managed emulators; `doctor` and the plugin warn if it's back on; upstream hook after AutoMap (ADR-001) |
| R15 | EmuDeck self-updates (`git pull` + `git reset --hard` at every launch) and changes behaviour under us | Medium | Medium | Never modify EmuDeck's tree; pin tested EmuDeck commits in CI fixtures; `doctor` reports the EmuDeck commit |
| R16 | **Decky store won't accept LLM-written plugins** (wiki: "We do not accept any plugin that uses any LLM based code"; PR template checkbox "Generative AI was NOT used to write a majority of the code") | Certain, if AI-assisted | High for distribution | Decide the distribution path up front (open question 10); see [14](14-packaging-permissions.md) |

## Open questions (decide before or during Phase 1)

1. **Content vs controller precedence.** Content-first is the default ([03 §3.1](03-canonical-model.md)). Validate with users: does "all DS4 for GC" vs "any controller for Melee" feel right? Alternatively, make it a global setting.
2. **Should shipped defaults reproduce EmuDeck exactly, or improve on it?** Recommendation: reproduce it exactly (zero visible change at install), and offer improvements as opt-in presets.
3. **Brand-level rules when style differs within a brand.** 8BitDo makes Nintendo-style (Pro 2) *and* Sega-style (M30) pads. A brand rule binding `face_*` positions is fine; label-match presets at brand level may be wrong. Should the UI warn when a brand contains several styles?
4. **Do style rules use label semantics or positional?** Proposal: always positional. Style only picks presets and glyphs.
5. **Per-player rules?** E.g. "P2 always gets southpaw". Probably via `device` level + pinned slots; a `player` scope could be added later.
6. **Handheld vs docked as a scope dimension?** E.g. "When docked, map GC with the DS4 differently". Could be a third scope axis `context: handheld|docked`. Deferred; keep the schema extensible (`applies_to` is an object).
7. **Name.** "map-helper" is a working title.
8. **License: decided, GPL-3.0** (see `LICENSE`). It matches EmuDeck (GPL-3.0, confirmed in S5/S7) and the EmuDeck config fixtures we redistribute. SDL_GameControllerDB is zlib-licensed, which is GPL-compatible.
9. **Upstream-first?** Pitch the pre-launch hook (and maybe the whole tool) to EmuDeck early, before investing in a separate Decky plugin.
10. **How do we ship the UI, given the Decky store's AI policy (R16)?** Options:
    (a) a Decky plugin distributed outside the store (GitHub Release zip, installed through Decky's manual install / developer mode);
    (b) a human-written Decky UI submitted to the store, with AI-assisted work limited to the core, if the store's reviewers accept that split;
    (c) a standalone full-screen app added to Steam as a non-Steam shortcut, with no Decky dependency (also sidesteps Decky's input-capture limits).
    Decide before Phase 3.
