// Copies the shared Python package next to the serverless function so Vercel bundles it.
// Runs before `next build` (see package.json). The copy is gitignored.
import { cpSync, rmSync, mkdirSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const web = join(dirname(fileURLToPath(import.meta.url)), "..");
const source = join(web, "..", "matchlens");
const target = join(web, "_py", "matchlens");

if (!existsSync(source)) {
  console.log("sync-python: ../matchlens not found, skipping (the _py copy must already exist)");
  process.exit(0);
}
rmSync(join(web, "_py"), { recursive: true, force: true });
mkdirSync(target, { recursive: true });
cpSync(join(source, "__init__.py"), join(target, "__init__.py"));
cpSync(join(source, "live"), join(target, "live"), { recursive: true, filter: (p) => !p.includes("__pycache__") });
console.log("sync-python: copied matchlens/live to web/_py");
