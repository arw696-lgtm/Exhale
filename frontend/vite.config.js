import { execSync } from "node:child_process";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/**
 * "Has it actually updated?" should be answerable by looking, not by guessing.
 *
 * A stale shell, a deploy that didn't run, and a change that simply isn't
 * visible all feel identical from a phone. Stamping the build turns that into
 * one glance at You → Settings.
 *
 * The commit is read at build time and is optional: the Docker build may not
 * carry a .git directory, in which case the timestamp alone still changes on
 * every build, which is the part that matters.
 */
function buildCommit() {
  if (process.env.EXHALE_BUILD_COMMIT) return process.env.EXHALE_BUILD_COMMIT;
  try {
    return execSync("git rev-parse --short HEAD", { stdio: ["ignore", "pipe", "ignore"] })
      .toString()
      .trim();
  } catch {
    return "";
  }
}

export default defineConfig({
  plugins: [react()],
  define: {
    __BUILD_COMMIT__: JSON.stringify(buildCommit()),
    __BUILD_TIME__: JSON.stringify(new Date().toISOString()),
  },
});
