import { definePlugin, routerHook } from "@decky/api";
import { staticClasses } from "@decky/ui";
import { FaGamepad } from "react-icons/fa";
import { ButtonMap } from "./map/ButtonMap";
import { MAP_ROUTE } from "./navigation";
import { Panel } from "./panel/Panel";
import { t } from "./strings";

export default definePlugin(() => {
  routerHook.addRoute(MAP_ROUTE, ButtonMap, { exact: true });

  return {
    name: t.title,
    titleView: <div className={staticClasses.Title}>{t.title}</div>,
    content: <Panel />,
    icon: <FaGamepad />,
    onDismount() {
      routerHook.removeRoute(MAP_ROUTE);
    },
  };
});
