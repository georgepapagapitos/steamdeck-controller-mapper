import { Navigation } from "@decky/ui";

export const MAP_ROUTE = "/map-helper/map";

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
