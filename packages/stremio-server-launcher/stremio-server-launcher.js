// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Juan Manuel Méndez Rey <vejeta@gmail.com>
//
// Run Stremio's streaming server. Its server.js is not free software, so it is
// not part of this package: it is downloaded from Stremio on the first start,
// checked against the sha256 below, kept in the data directory and run from there.
// Container images built from this package can therefore be redistributed.
//
// Environment:
//   STREMIO_SERVER_DIR  data directory (default: $HOME/.stremio-server), where
//                       the server keeps its cache and settings as well
//   STREMIO_SERVER_URL  where to download server.js from (a mirror)

"use strict";

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const VERSION = "@VERSION@";
const SHA256 = "@SHA256@";

function fail(message) {
  console.error("stremio-server: " + message);
  process.exit(1);
}

async function download(url, file) {
  console.log("stremio-server: downloading " + url);
  const res = await fetch(url);
  if (!res.ok) fail("download failed: HTTP " + res.status + " for " + url);
  const data = Buffer.from(await res.arrayBuffer());
  const sum = crypto.createHash("sha256").update(data).digest("hex");
  if (sum !== SHA256) fail("checksum mismatch for " + url + ": " + sum + ", expected " + SHA256);
  fs.writeFileSync(file + ".tmp", data);
  fs.renameSync(file + ".tmp", file);
  console.log("stremio-server: installed " + file);
}

async function main() {
  const home = process.env.HOME || "/tmp";
  const dir = process.env.STREMIO_SERVER_DIR || path.join(home, ".stremio-server");
  const file = path.join(dir, "server-" + VERSION + ".js");
  fs.mkdirSync(dir, { recursive: true });
  if (!fs.existsSync(file)) {
    const url = process.env.STREMIO_SERVER_URL ||
      "https://dl.strem.io/server/v" + VERSION + "/desktop/server.js";
    await download(url, file);
  }
  // the server keeps its cache and settings in APP_PATH (default ~/.stremio-server)
  process.env.APP_PATH = process.env.APP_PATH || dir;
  process.env.FFMPEG_BIN = process.env.FFMPEG_BIN || "/usr/bin/ffmpeg";
  process.env.FFPROBE_BIN = process.env.FFPROBE_BIN || "/usr/bin/ffprobe";
  require(file);
}

main().catch((err) => fail(err && err.message ? err.message : String(err)));
