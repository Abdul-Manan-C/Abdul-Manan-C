#!/usr/bin/env node
/**
 * Evaluate JavaScript on a live page and print the result as JSON.
 *
 *   node scripts/cdp_eval.mjs <url> <expression-file> [waitMs]
 *
 * Used to measure how GitHub actually renders the profile README (column
 * width, image sizes) instead of guessing at the CSS.
 */

import { spawn } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import { join } from "node:path";
import { tmpdir } from "node:os";

const [url, expressionFile, waitArg] = process.argv.slice(2);
if (!url || !expressionFile) {
  console.error("usage: node scripts/cdp_eval.mjs <url> <expression-file> [waitMs]");
  process.exit(2);
}

const WAIT_MS = Number(waitArg || 8000);

const CHROME_CANDIDATES = [
  process.env.CHROME_BIN,
  "google-chrome",
  "google-chrome-stable",
  "chromium",
  "chromium-browser",
].filter(Boolean);

function findChrome() {
  for (const name of CHROME_CANDIDATES) {
    if (name.includes("/") && existsSync(name)) return name;
    for (const dir of (process.env.PATH || "").split(":")) {
      const candidate = join(dir, name);
      if (existsSync(candidate)) return candidate;
    }
  }
  return "";
}

function freePort() {
  return new Promise((resolvePort, reject) => {
    const server = createServer();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      server.close(() => resolvePort(port));
    });
  });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const chrome = findChrome();
  if (!chrome) {
    console.error("no chrome binary found");
    return 2;
  }
  const port = await freePort();
  const profile = join(tmpdir(), `cdp-eval-${process.pid}`);
  const chromeProcess = spawn(
    chrome,
    [
      "--headless=new",
      "--disable-gpu",
      "--no-sandbox",
      "--disable-dev-shm-usage",
      "--hide-scrollbars",
      "--no-first-run",
      `--user-data-dir=${profile}`,
      `--remote-debugging-port=${port}`,
      `--window-size=${process.env.CDP_WINDOW || "1280,900"}`,
      "about:blank",
    ],
    { stdio: "ignore" },
  );

  let ready = false;
  for (let i = 0; i < 60; i += 1) {
    await sleep(500);
    try {
      if ((await fetch(`http://127.0.0.1:${port}/json/version`)).ok) {
        ready = true;
        break;
      }
    } catch {
      /* not up yet */
    }
  }
  if (!ready) {
    chromeProcess.kill();
    console.error("chrome devtools endpoint did not start");
    return 2;
  }

  const created = await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(url)}`, {
    method: "PUT",
  }).then((r) => r.json());

  const socket = new WebSocket(created.webSocketDebuggerUrl);
  await new Promise((res, rej) => {
    socket.addEventListener("open", res);
    socket.addEventListener("error", rej);
  });

  let id = 0;
  const pending = new Map();
  socket.addEventListener("message", (event) => {
    const msg = JSON.parse(event.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve: ok, reject: fail } = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) fail(new Error(msg.error.message));
      else ok(msg.result);
    }
  });
  const send = (method, params = {}) =>
    new Promise((ok, fail) => {
      id += 1;
      pending.set(id, { resolve: ok, reject: fail });
      socket.send(JSON.stringify({ id, method, params }));
    });

  await send("Page.enable");
  await send("Runtime.enable");

  // Chrome on Linux refuses a window narrower than ~500px, so a phone
  // viewport has to be emulated rather than resized.
  const emulateWidth = Number(process.env.CDP_EMULATE_WIDTH || 0);
  if (emulateWidth) {
    const emulateHeight = Number(process.env.CDP_EMULATE_HEIGHT || 844);
    const scale = Number(process.env.CDP_EMULATE_SCALE || 2);
    await send("Emulation.setDeviceMetricsOverride", {
      width: emulateWidth,
      height: emulateHeight,
      deviceScaleFactor: scale,
      mobile: true,
    });
    await send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 });
  }

  await send("Page.navigate", { url });
  await sleep(WAIT_MS);

  const expression = readFileSync(expressionFile, "utf-8");
  const result = await send("Runtime.evaluate", {
    expression: `(() => { ${expression} })()`,
    returnByValue: true,
    awaitPromise: true,
  });

  // Optional full-page screenshot - the only way to capture a viewport that
  // is narrower than Chrome's minimum window size.
  const shotPath = process.env.CDP_SCREENSHOT;
  if (shotPath) {
    const metrics = await send("Page.getLayoutMetrics");
    const { contentSize } = metrics;
    const shot = await send("Page.captureScreenshot", {
      format: "png",
      captureBeyondViewport: true,
      clip: {
        x: 0,
        y: 0,
        width: contentSize.width,
        height: contentSize.height,
        scale: 1,
      },
    });
    writeFileSync(shotPath, Buffer.from(shot.data, "base64"));
  }

  console.log(JSON.stringify(result.result.value ?? result.result.description, null, 2));
  socket.close();
  chromeProcess.kill();
  return 0;
}

main().then((code) => process.exit(code));
