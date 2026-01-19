#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


# --- Patch 1: Make pxtConfig URL bases absolute (route-agnostic) ---
RUNTIME_PATCH = """\
(function () {
  try {
    // Base = origin + relprefix (relprefix will be "/" if built with --route /)
    var rel = (window.pxtConfig && pxtConfig.relprefix) ? pxtConfig.relprefix : "/";
    var base = window.location.origin + rel;

    // MakeCode sometimes uses these as *bases* for new URL(relative, base)
    // In self-hosted/static builds, keeping them absolute avoids "Invalid base URL".
    function abs(u) {
      if (!u) return u;
      // already absolute
      if (/^https?:\\/\\//.test(u)) return u;
      // site-absolute
      if (u[0] === "/") return window.location.origin + u;
      // relative to relprefix base
      return base + u;
    }

    // Normalize base-ish fields
    ["cdnUrl", "pxtCdnUrl", "commitCdnUrl", "blobCdnUrl"].forEach(function (k) {
      if (pxtConfig[k]) pxtConfig[k] = abs(pxtConfig[k]);
      else pxtConfig[k] = base;
    });

    // Normalize common entry points too (harmless if already absolute)
    ["simUrl", "docsUrl", "partsUrl", "runUrl", "multiUrl", "asseteditorUrl",
     "kioskUrl", "teachertoolUrl", "tutorialtoolUrl", "skillmapUrl",
     "multiplayerUrl", "authcodeUrl"].forEach(function (k) {
      if (pxtConfig[k]) pxtConfig[k] = abs(pxtConfig[k]);
    });
  } catch (e) {
    console.warn("patch-staticpkg-index: failed to absolutize pxtConfig", e);
  }
})();
"""


# --- Patch 2: Optional: Inject SIM bridge logic directly into MakeCode page ---
# If you want this now, set ENABLE_BRIDGE = True.
ENABLE_BRIDGE = True

BRIDGE_PATCH = r"""
(function () {
  // ===== micro:bit SIM serial bridge (injected into MakeCode top-level page) =====
  // postMessage API:
  //   incoming:  {type:"SIM_CONNECT"} / {type:"SIM_SERIAL_IN", line:"..."}
  //   outgoing:  {type:"SIM_CONNECTED"} / {type:"SIM_READY"} / {type:"SIM_SERIAL_OUT", line:"..."}

  function isAllowedOrigin(origin) {
    if (origin === "null") return true;                 // some browsers for file://
    if (typeof origin === "string" && origin.indexOf("file://") === 0) return true;

    // local dev servers (optional)
    if (origin === "http://localhost:8000") return true;
    if (origin === "http://127.0.0.1:8000") return true;
    if (origin === "http://localhost:5173") return true;
    if (origin === "http://127.0.0.1:5173") return true;

    return false;
  }

  var STATE = {
    peer: null,
    peerOrigin: null,
    rxBuf: "",
    pendingOut: [],
    tapBoard: null,
    tapSimWin: null
  };

  //function sendToPeer(msg) {
  //  if (STATE.peer && STATE.peerOrigin) {
  //    STATE.peer.postMessage(msg, STATE.peerOrigin);
  //  }
  //}

  function sendToPeer(msg) {
    // If we have a connected peer, try to send safely
    if (STATE.peer) {
      try {
        // If the peer's origin is "null" (file://), you can't use it as targetOrigin.
        const target = (STATE.peerOrigin === "null" || !STATE.peerOrigin) ? "*" : STATE.peerOrigin;
        STATE.peer.postMessage(msg, target);
        return;
      } catch (e) {}
    }

    // Fallback: if MakeCode was opened by the template, reply to opener
    if (window.opener && window.opener !== window) {
      try {
        window.opener.postMessage(msg, "*");
        return;
      } catch (e2) {}
    }
  }

  function findSimWindow(win) {
    try {
      if (win && win.pxsim && win.pxsim.serial && win.pxsim.serial.inject) return win;
    } catch (e) {}
    try {
      var n = (win && win.frames) ? win.frames.length : 0;
      for (var i = 0; i < n; i++) {
        var found = findSimWindow(win.frames[i]);
        if (found) return found;
      }
    } catch (e2) {}
    return null;
  }

  function isSimLive(simWin) {
    try {
      var rt = simWin && simWin.pxsim && simWin.pxsim.runtime;
      // tolerate versions where running flag isn't reliable
      return !!(rt && !rt.dead && (rt.running || rt.running === undefined));
    } catch (e) {
      return false;
    }
  }

  function installSerialTap(simWin) {
    var px = simWin && simWin.pxsim;
    var ser = px && px.serial;
    if (!ser || !ser.writeString) return;

    var b = null;
    try { b = px.board && px.board(); } catch (e) {}
    if (!b) return;

    var isNewRun = (STATE.tapBoard !== b) || (STATE.tapSimWin !== simWin);
    if (isNewRun) {
      STATE.tapBoard = b;
      STATE.tapSimWin = simWin;
      STATE.rxBuf = "";
    }

    if (!ser.__bridgeOrigWriteString) {
      ser.__bridgeOrigWriteString = ser.writeString.bind(ser);
    } else if (isNewRun) {
      // restore original before rewrapping
      ser.writeString = ser.__bridgeOrigWriteString;
    }

    if (ser.__bridgeTapInstalled && !isNewRun) return;
    ser.__bridgeTapInstalled = true;

    var orig = ser.__bridgeOrigWriteString;

    ser.writeString = function (s) {
      STATE.rxBuf += String(s == null ? "" : s);
      if (/\n/.test(STATE.rxBuf)) {
        var parts = STATE.rxBuf.split(/\r?\n/);
        STATE.rxBuf = parts.pop() || "";
        for (var i = 0; i < parts.length; i++) {
          var line = parts[i];
          if (!line) continue;
          sendToPeer({ type: "SIM_SERIAL_OUT", line: line });
        }
      }
      return orig(s);
    };

    sendToPeer({ type: "SIM_READY" });
  }

  function tryFlushPending(simWin) {
    if (!simWin) return;
    if (!isSimLive(simWin)) return;

    while (STATE.pendingOut.length) {
      var payload = STATE.pendingOut.shift();
      try {
        simWin.pxsim.serial.inject(payload);
      } catch (e) {
        STATE.pendingOut.unshift(payload);
        break;
      }
    }
  }

  function injectLine(line) {
    var simWin = findSimWindow(window);
    if (!simWin) return false;

    var payload = (line && line.endsWith && line.endsWith("\n")) ? line : (String(line) + "\n");

    if (!isSimLive(simWin)) {
      STATE.pendingOut.push(payload);
      return true;
    }

    simWin.pxsim.serial.inject(payload);
    return true;
  }

  window.addEventListener("message", function (ev) {
    if (!isAllowedOrigin(ev.origin)) return;

    var msg = ev.data;
    if (!msg || typeof msg !== "object") return;

    if (msg.type === "SIM_CONNECT") {
      STATE.peer = ev.source;
      STATE.peerOrigin = ev.origin;
      sendToPeer({ type: "SIM_CONNECTED" });

      var simWin = findSimWindow(window);
      if (simWin && isSimLive(simWin)) sendToPeer({ type: "SIM_READY" });
      return;
    }

    if (msg.type === "SIM_SERIAL_IN") {
      var line =
        (typeof msg.line === "string" && msg.line) ||
        (typeof msg.text === "string" && msg.text) ||
        (typeof msg.data === "string" && msg.data) ||
        (typeof msg.msg === "string" && msg.msg) ||
        "";
      if (!line) return;
      injectLine(line);
      return;
    }
  });

  setInterval(function () {
    var simWin = findSimWindow(window);
    if (!simWin) return;
    installSerialTap(simWin);
    tryFlushPending(simWin);
  }, 250);
})();
"""


PATCH_SENTINEL_1 = "patch-staticpkg-index: failed to absolutize pxtConfig"
PATCH_SENTINEL_2 = "micro:bit SIM serial bridge (injected into MakeCode top-level page)"


def patch_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8")

    # Find where pxtConfig is defined
    marker = "var pxtConfig = {"
    start = text.find(marker)
    if start == -1:
        raise SystemExit(f"ERROR: couldn't find '{marker}' in {path}")

    # End of config object "};"
    end = text.find("\n};", start)
    if end == -1:
        end = text.find("};", start)
        if end == -1:
            raise SystemExit(f"ERROR: couldn't find end of pxtConfig object ('}};') after marker in {path}")

    insert_at = end + (len("\n};") if text[end:end+3] == "\n};" else 2)

    patched = text

    # Insert Patch 1 (idempotent)
    if PATCH_SENTINEL_1 not in patched:
        patched = patched[:insert_at] + "\n" + RUNTIME_PATCH + patched[insert_at:]
        # update insert_at because we inserted text
        insert_at = insert_at + 1 + len(RUNTIME_PATCH)

    # Replace @cdnUrl@ tokens in a route-agnostic way:
    # use relprefix if possible; else fall back to "/"
    # This avoids hard-coding "/editor" when you move to route "/".
    # We do a conservative replacement: @cdnUrl@ -> "" (empty) because links already start with "/blob/..."
    # If you see broken icons again, we can change to (pxtConfig.cdnUrl without origin) later.
    patched = patched.replace("@cdnUrl@", "")

    # Insert bridge patch (optional + idempotent)
    if ENABLE_BRIDGE and PATCH_SENTINEL_2 not in patched:
        # safest: insert a separate <script> near end of body
        needle = "</body>"
        idx = patched.rfind(needle)
        if idx == -1:
            raise SystemExit(f"ERROR: couldn't find </body> in {path}")
        injected = "\n<script>\n" + BRIDGE_PATCH + "\n</script>\n"
        patched = patched[:idx] + injected + patched[idx:]

    path.write_text(patched, encoding="utf-8")
    print(f"Patched: {path}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: patch-staticpkg-index.py <path-to-index.html>")

    path = Path(sys.argv[1])
    if not path.is_file():
        raise SystemExit(f"ERROR: not found: {path}")

    patch_file(path)


if __name__ == "__main__":
    main()