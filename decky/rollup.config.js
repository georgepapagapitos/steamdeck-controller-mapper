import deckyPlugin from "@decky/rollup";
import { resolve } from "path";

// Development only: `pnpm run build:fixture` (rollup --environment MH_FIXTURE) builds the frontend with a
// canned backend answer, so the UI can be looked at without the core or a launch. `MH_FIXTURE` alone answers
// with dev/last-launch.json; `--environment MH_FIXTURE:no-launch` answers with dev/responses/no-launch.json.
// A normal build resolves the module to `null`, and package.sh refuses a bundle that contains sample data.
const FIXTURE_ID = "mh:fixture";

function devPath(...parts) {
  return JSON.stringify(resolve("dev", ...parts).split("\\").join("/"));
}

function fixture() {
  const name = process.env.MH_FIXTURE;
  return {
    name: "map-helper-fixture",
    resolveId(id) {
      return id === FIXTURE_ID ? `\0${FIXTURE_ID}` : null;
    },
    load(id) {
      if (id !== `\0${FIXTURE_ID}`) return null;
      if (!name) return "export default null;";
      if (name === "true" || name === "ok") {
        return `import data from ${devPath("last-launch.json")};\nexport default { ok: true, data, sample: true };`;
      }
      return `import answer from ${devPath("responses", `${name}.json`)};\nexport default { ...answer, sample: true };`;
    },
  };
}

export default deckyPlugin({
  plugins: [fixture()],
});
