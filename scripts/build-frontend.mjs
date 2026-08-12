import { cp, mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";

const root = process.cwd();
const source = path.join(root, "webapp", "static");
const output = path.join(root, "frontend-dist");
const assets = path.join(output, "assets");
const apiBaseUrl = String(process.env.API_BASE_URL || "").trim().replace(/\/$/, "");

if (process.env.VERCEL && !apiBaseUrl) {
  throw new Error("API_BASE_URL is required. Set it to the Railway public URL.");
}
if (apiBaseUrl && !/^https:\/\//i.test(apiBaseUrl)) {
  throw new Error("API_BASE_URL must start with https://");
}

await rm(output, { recursive: true, force: true });
await mkdir(assets, { recursive: true });
await cp(source, assets, { recursive: true });
await cp(path.join(source, "index.html"), path.join(output, "index.html"));
await cp(path.join(source, "admin.html"), path.join(output, "admin.html"));
await cp(path.join(root, "logo.ico"), path.join(output, "logo.ico"));

await writeFile(
  path.join(assets, "config.js"),
  `window.BROOST_CONFIG = Object.freeze({ apiBaseUrl: ${JSON.stringify(apiBaseUrl)} });\n`,
  "utf8",
);

// Keep Vercel's clean /admin route and avoid publishing the source HTML twice.
await Promise.all([
  rm(path.join(assets, "index.html"), { force: true }),
  rm(path.join(assets, "admin.html"), { force: true }),
]);
const imageDirectory = path.join(assets, "images");
const imageFiles = await readdir(imageDirectory);
const publishedPngAssets = new Set([
  "exec-5bc8657c-2aef-41cf-8e24-46bb94fc5556.png",
  "exec-eb691454-04b6-402a-83ca-e8a6a3761f30.png",
]);
await Promise.all(
  imageFiles
    .filter(
      (filename) =>
        filename.toLowerCase().endsWith(".png") && !publishedPngAssets.has(filename),
    )
    .map((filename) => rm(path.join(imageDirectory, filename), { force: true })),
);

const indexHtml = await readFile(path.join(output, "index.html"), "utf8");
if (!indexHtml.includes("/assets/config.js")) {
  throw new Error("Frontend build is missing the runtime API configuration script.");
}
