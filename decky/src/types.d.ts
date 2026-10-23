declare module "mh:fixture" {
  // A canned backend answer in fixture builds, null in real ones (see rollup.config.js).
  const response: import("./data").LastLaunchResult | null;
  export default response;
}

declare module "mh:kenney" {
  // Kenney's Input Prompts SVGs in assets/kenney/, by file name without .svg (see rollup.config.js).
  const icons: Record<string, string>;
  export default icons;
}
