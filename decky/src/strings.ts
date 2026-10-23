// Every user-visible string in one place, so a translation only has to replace this file (docs/08: localisation-ready).

export const t = {
  title: "map-helper",
  sample: "Sample data: a development build, not your last game.",

  loading: "Reading the last launch…",
  retry: "Try again",
  refresh: "Refresh",

  errors: {
    noBackend: "The map-helper plugin's backend isn't answering. Try reloading the plugin.",
    badAnswer: "The plugin's backend gave an answer it couldn't read.",
  },

  states: {
    notInstalledTitle: "map-helper not installed",
    notInstalledBody:
      "The plugin is here, but the map-helper core isn't installed on this Deck yet. Install it from a computer with tools/deck.sh install.",
    noLaunchTitle: "Nothing launched yet",
    noLaunchBody:
      "Start a game from ES-DE or a Steam shortcut that runs through map-helper. What each button does will show up here.",
    errorTitle: "Couldn't read the last launch",
  },

  nowPlaying: "Now playing",
  unknownGame: "Unknown game",
  outcome: {
    changed: "Mappings applied at launch",
    "no-changes": "Mappings already in place at launch",
    skipped: "map-helper left this launch alone",
    error: "Mappings couldn't be applied at launch",
  } as Record<string, string>,
  outcomeUnknown: (outcome: string) => `Launch result: ${outcome}`,

  players: "Players",
  noPlayers: "No controllers were connected at launch.",
  playerShort: (n: number) => `P${n}`,
  playerLong: (n: number) => `Player ${n}`,
  openPlayer: (n: number, pad: string) => `Show the button map for player ${n}, ${pad}`,
  showButtonMap: "Show button map",

  whoIsP1: "Who is player 1?",
  policy: {
    "steam-order-es-de":
      "The first pad you press after starting ES-DE. To change it, restart ES-DE and press a button on that pad first.",
    "steam-order":
      "The first pad you press after the game starts: Steam's controller order. Restart the game and press a button on that pad first to change it.",
    "external-first": "Docked: your own controllers come first, in Steam's order. The Deck's controls come last.",
    pinned: "You pinned controllers to players in map-helper.",
    "deck-only": "Only the Deck's own controls are used.",
  } as Record<string, string>,
  policyUnknown: (name: string) => `Player order: ${name}.`,
  policyWhy: (reason: string) => `Why: ${reason}`,

  lastLaunch: "Last launch",
  launchedFrom: "Launched from",
  appliedLabel: "Applied in",
  appliedIn: (ms: number) => `${ms} ms`,
  modes: { "es-de": "ES-DE", steam: "Steam shortcut", show: "Preview (map-helper show)" } as Record<string, string>,
  today: "Today",
  yesterday: "Yesterday",

  map: {
    back: "Back to the game",
    asApplied: "as applied at launch",
    playerTabs: "Players",
    drawing: (pad: string) => `${pad}: buttons and what they do`,
    inputs: "Buttons",
    nothing: "Nothing",
    nothingLong: "Does nothing in this game",
    clash: "Drives more than one thing: two mappings clash here.",
    changeButton: "Change button",
    comingSoon: "Coming soon",
    gameSees: "Game sees it as",
    noInputs: "map-helper doesn't know this controller's buttons.",
    noPlayers: "No controllers were connected at launch, so there is nothing to show.",
    selectHint: "Select a button to see what it does.",
    backPaddles: "Back paddles",
    backButtons: "Back buttons",
    steamOnly: "Steam Input only",
    extraButtons: "Extra buttons",
    backAndExtra: "Back and extra buttons",
    steamOnlyNoteDeck: "Not seen by emulators: set them in Steam Input.",
    steamOnlyNote: "Not seen by emulators: set them in Steam Input or the controller's own app.",
    steamOnlyDetail: "Emulators never see this button: they get Steam's virtual Xbox 360 pad, which has none.",
    legend: "Where each mapping comes from",
    select: "Select",
    goBack: "Back",
    warnings: "Warnings",
  },

  source: {
    rule: "Your rule",
    emulator: "Emulator default",
    emudeck: "EmuDeck",
    unknown: "Other",
  } as Record<string, string>,

  options: {
    percent: (n: number) => `${Math.round(n * 100)}%`,
    on: "On",
    off: "Off",
  },
};
