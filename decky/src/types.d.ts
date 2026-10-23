declare module "mh:fixture" {
  // A canned backend answer in fixture builds, null in real ones (see rollup.config.js).
  const response: import("./data").LastLaunchResult | null;
  export default response;
}
