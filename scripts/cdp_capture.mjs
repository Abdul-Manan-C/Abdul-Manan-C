#!/usr/bin/env node
/**
 * Capture live platform screenshots for the profile README.
 *
 * Chrome DevTools Protocol over Node's built-in WebSocket (no npm packages).
 * Each URL is opened, allowed to settle on real network time, then captured
 * at 1440x900 as a JPEG.
 *
 *   node scripts/cdp_capture.mjs assets/screens
 *
 * A target that fails keeps the screenshot it already has, so the gallery
 * never breaks when a client site is temporarily unavailable.
 */

import { spawn } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import { join, resolve } from "node:path";
import { tmpdir } from "node:os";

const TARGETS = [
  ["laxitech", "https://laxitech.com/"],
  ["vixion", "https://www.vixion.studio/"],
  ["movix", "https://www.movixstudio.com/"],
  ["commerce-lions", "https://www.commercelions.com/"],
  ["super-luxuries", "https://www.superluxuries.store/"],
  ["mac-vision", "https://www.macvision.store/"],
];

const WIDTH = 1440;
const HEIGHT = 900;
const SETTLE_MS = 9000;
const MAX_WAIT_MS = 40000;

const UA =
  "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) " +
  "Chrome/126.0.0.0 Safari/537.36";

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

class CDP {
  constructor(url) {
    this.url = url;
    this.id = 0;
    this.pending = new Map();
    this.listeners = new Map();
    this.socket = new WebSocket(url);
    this.ready = new Promise((res, rej) => {
      this.socket.addEventListener("open", () => res());
      this.socket.addEventListener("error", (e) => rej(e));
    });
    this.socket.addEventListener("message", (event) => {
      const msg = JSON.parse(event.data);
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve: ok, reject: fail } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        if (msg.error) fail(new Error(msg.error.message));
        else ok(msg.result);
        return;
      }
      const handlers = this.listeners.get(msg.method) || [];
      this.listeners.delete(msg.method);
      handlers.forEach((fn) => fn(msg.params));
    });
  }

  send(method, params = {}) {
    const id = ++this.id;
    return new Promise((ok, fail) => {
      this.pending.set(id, { resolve: ok, reject: fail });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  once(method, timeoutMs) {
    return new Promise((ok) => {
      const handler = (params) => ok(params);
      this.listeners.set(method, [handler]);
      setTimeout(() => {
        if (this.listeners.get(method)) {
          this.listeners.delete(method);
          ok(null);
        }
      }, timeoutMs);
    });
  }

  close() {
    try {
      this.socket.close();
    } catch {
      /* already closed */
    }
  }
}

async function captureOne(port, slug, url, outDir) {
  const created = await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(url)}`, {
    method: "PUT",
  }).then((r) => r.json());

  const client = new CDP(created.webSocketDebuggerUrl);
  await client.ready;

  let inFlight = 0;
  let quietSince = Date.now();
  let loaded = false;

  client.listeners.set("Network.requestWillBeSent", [
    () => {
      inFlight += 1;
      quietSince = Date.now();
    },
  ]);
  client.listeners.set("Network.loadingFinished", [
    () => {
      inFlight = Math.max(0, inFlight - 1);
      quietSince = Date.now();
    },
  ]);
  client.listeners.set("Network.loadingFailed", [
    () => {
      inFlight = Math.max(0, inFlight - 1);
      quietSince = Date.now();
    },
  ]);
  client.listeners.set("Page.loadEventFired", [
    () => {
      loaded = true;
      quietSince = Date.now();
    },
  ]);

  await client.send("Page.enable");
  await client.send("Network.enable");
  await client.send("Runtime.enable");
  await client.send("Emulation.setDeviceMetricsOverride", {
    width: WIDTH,
    height: HEIGHT,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await client.send("Page.navigate", { url });

  const deadline = Date.now() + MAX_WAIT_MS;
  while (Date.now() < deadline) {
    await sleep(400);
    if (loaded && inFlight === 0 && Date.now() - quietSince > SETTLE_MS) break;
  }

  await client.send("Runtime.evaluate", {
    expression:
      "document.fonts ? document.fonts.ready.then(()=>1) : 1; window.scrollTo(0,0); 1",
    awaitPromise: true,
  });
  await sleep(1200);

  const shot = await client.send("Page.captureScreenshot", {
    format: "jpeg",
    quality: 84,
    captureBeyondViewport: false,
  });

  const file = join(outDir, `${slug}.jpg`);
  writeFileSync(file, Buffer.from(shot.data, "base64"));
  client.close();
  await fetch(`http://127.0.0.1:${port}/json/close/${created.id}`).catch(() => {});
  return file;
}

async function main() {
  const outDir = resolve(process.argv[2] || "assets/screens");
  mkdirSync(outDir, { recursive: true });

  const chrome = findChrome();
  if (!chrome) {
    console.error("no chrome binary found; keeping previous screenshots");
    return 0;
  }

  const port = await freePort();
  const profile = join(tmpdir(), `profile-shots-${process.pid}`);
  const chromeProcess = spawn(
    chrome,
    [
      "--headless=new",
      "--disable-gpu",
      "--no-sandbox",
      "--disable-dev-shm-usage",
      "--hide-scrollbars",
      "--no-first-run",
      "--disable-extensions",
      "--disable-background-networking",
      `--user-data-dir=${profile}`,
      `--remote-debugging-port=${port}`,
      `--window-size=${WIDTH},${HEIGHT}`,
      `--user-agent=${UA}`,
      "about:blank",
    ],
    { stdio: "ignore" },
  );

  let ready = false;
  for (let i = 0; i < 60; i += 1) {
    await sleep(500);
    try {
      const res = await fetch(`http://127.0.0.1:${port}/json/version`);
      if (res.ok) {
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
    return 0;
  }

  let ok = 0;
  for (const [slug, url] of TARGETS) {
    try {
      const file = await captureOne(port, slug, url, outDir);
      const { statSync } = await import("node:fs");
      console.log(`  captured ${slug} -> ${file} (${Math.round(statSync(file).size / 1024)} KB)`);
      ok += 1;
    } catch (err) {
      console.error(`  failed   ${slug}: ${err && err.message ? err.message : err}`);
    }
  }

  chromeProcess.kill();
  console.log(`screenshots: ${ok}/${TARGETS.length} refreshed`);
  return 0;
}

main().then((code) => process.exit(code));
