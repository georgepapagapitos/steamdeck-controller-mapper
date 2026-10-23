import { Navigation } from "@decky/ui";

export const MAP_ROUTE = "/map-helper/map";
export const RULES_ROUTE = "/map-helper/rules";

// The player tab the button map opens on. Set just before navigating; the route reads it once when it mounts.
let requestedPlayer = 0;

export function openButtonMap(playerIndex = 0) {
  requestedPlayer = playerIndex;
  Navigation.Navigate(MAP_ROUTE);
  Navigation.CloseSideMenus();
}

export function takeRequestedPlayer(): number {
  const index = requestedPlayer;
  requestedPlayer = 0;
  return index;
}

export function openRulesPage() {
  Navigation.Navigate(RULES_ROUTE);
  Navigation.CloseSideMenus();
}
