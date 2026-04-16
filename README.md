# Holafly QA Tool

A CLI + TUI tool for QA engineers testing the Holafly Flutter eSIM app. It automates the full network interception workflow: running mitmproxy as a proxy, booting an Android emulator routed through it, installing the CA certificate into the system trust store, and injecting failure scenarios (HTTP errors, dropped connections) per endpoint — all without touching a single config file manually.

---

## Prerequisites

All of the following must be installed and on your `PATH` before using `qa-tool`.

### Python 3.11+

```bash
python3 --version
```

Install via your system package manager or [python.org](https://www.python.org/downloads/). Python 3.11+ is required for the built-in `tomllib` module.

### Android Studio + Emulator

Install [Android Studio](https://developer.android.com/studio). After installation, make sure the following are on your `PATH` (usually under `~/Android/Sdk/`):

| Binary | Location |
|--------|----------|
| `adb` | `~/Android/Sdk/platform-tools/` |
| `emulator` | `~/Android/Sdk/emulator/` |

Add to `~/.bashrc` or `~/.zshrc`:

```bash
export ANDROID_HOME="$HOME/Android/Sdk"
export PATH="$PATH:$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator"
```

Create at least one AVD using the Android Studio AVD Manager. **Important:** use a `google_apis` image (not `google_apis_playstore`). Play Store images block `adb root`, which is required for cert installation. API 33 or API 35 is recommended.

### mitmproxy

```bash
pipx install mitmproxy
```

Or with pip:

```bash
pip install mitmproxy
```

Verify: `mitmweb --version`

### openssl

Usually pre-installed on macOS and Linux. Verify:

```bash
openssl version
```

On Ubuntu: `sudo apt install openssl`

### pipx (recommended for tool install)

```bash
pip install pipx
pipx ensurepath
```

After running `pipx ensurepath`, restart your terminal.

---

## Installing the Tool

### Development install (recommended)

Clone the repo and install in editable mode so changes to source take effect immediately:

```bash
cd /path/to/qa_tool
pipx install --editable .
```

Or with a virtual environment:

```bash
pip install -e ".[dev]"
```

Verify:

```bash
qa-tool --help
```

---

## Quick Start

The first time you set up a device for testing, run through these steps in order.

```bash
# 1. Pick your AVD and create the config
qa-tool init

# 2. Check all dependencies are installed and on PATH
qa-tool doctor

# 3. Start the proxy
qa-tool mitmweb start

# 4. Start the emulator (routed through the proxy)
qa-tool emulator start

# 5. Install the mitmproxy CA cert into the system trust store
#    (takes 2-3 minutes — includes a remount + reboot cycle)
qa-tool cert install

# 6. Drop an APK into the apks/ folder at the project root, then install it
qa-tool apk install

# 7. Or launch the TUI and do everything from one screen
qa-tool gui
```

After the initial cert install, subsequent sessions only need steps 3, 4, and 6 — or just `qa-tool gui`.

---

## CLI Reference

### `qa-tool init`

Interactive setup. Detects available AVDs and writes `~/.holafly-qa/config.toml`.

```bash
qa-tool init
```

Run this once when first setting up, or when switching to a different AVD.

---

### `qa-tool doctor`

Checks that `adb`, `emulator`, `mitmweb`, `python3`, and `openssl` are installed and accessible on `PATH`.

```bash
qa-tool doctor
```

---

### `qa-tool version`

```bash
qa-tool version
```

---

### `qa-tool mitmweb`

| Command | Description |
|---------|-------------|
| `qa-tool mitmweb start` | Start mitmproxy in the background |
| `qa-tool mitmweb stop` | Stop the background mitmproxy process |

```bash
# Start on the default port (8080)
qa-tool mitmweb start

# Start on a custom port
qa-tool mitmweb start --port 9090

# Stop
qa-tool mitmweb stop
```

The web UI is available at `http://127.0.0.1:8081` while mitmweb is running. Logs go to `~/.holafly-qa/mitmweb.log`.

---

### `qa-tool emulator`

| Command | Description |
|---------|-------------|
| `qa-tool emulator start` | Boot the AVD with proxy-friendly flags |
| `qa-tool emulator stop` | Gracefully shut down the emulator |
| `qa-tool emulator wipe-app` | Clear app data (keeps cert and other apps) |
| `qa-tool emulator wipe-data` | Factory reset (wipes everything including the cert) |

```bash
# Start with proxy (default)
qa-tool emulator start

# Start without proxy — use this when testing Adyen payments
qa-tool emulator start --no-proxy

# Start and return immediately without waiting for boot
qa-tool emulator start --no-wait

# Stop
qa-tool emulator stop

# Clear only the Holafly app data (no reboot needed)
qa-tool emulator wipe-app

# Clear a different package
qa-tool emulator wipe-app --package com.example.other

# Factory reset (prompts for confirmation)
qa-tool emulator wipe-data

# Factory reset without confirmation prompt
qa-tool emulator wipe-data --yes
```

The emulator boots with `-gpu host -cores 4 -memory 4096 -writable-system -no-snapshot`. The `-http-proxy` flag is passed at the QEMU level so Flutter's Dart HttpClient respects it (Android system proxy settings are bypassed by Flutter).

---

### `qa-tool cert`

| Command | Description |
|---------|-------------|
| `qa-tool cert install` | Push the mitmproxy CA cert to the system trust store |

```bash
qa-tool cert install
```

Requires the emulator to be running. Takes 2-3 minutes due to a `adb remount` + reboot cycle. The cert is installed to `/system/etc/security/cacerts/` and survives app reinstalls. It is wiped by `emulator wipe-data`.

---

### `qa-tool apk`

| Command | Description |
|---------|-------------|
| `qa-tool apk install` | Install an APK from the `apks/` folder |

```bash
# Auto-discover from the apks/ folder
qa-tool apk install

# Install a specific file
qa-tool apk install --path ~/Downloads/holafly-1.2.3.apk

# Install without removing the previous version first
qa-tool apk install --keep
```

Drop APK files from Codemagic into the `apks/` folder at the project root. If there is exactly one APK, it installs automatically. If there are multiple, an interactive picker appears.

---

### `qa-tool inject`

Manage failure injection rules — make specific endpoints return HTTP errors or drop connections.

| Command | Description |
|---------|-------------|
| `qa-tool inject list` | Show all rules and which is active |
| `qa-tool inject start <name>` | Activate a rule (restarts mitmweb with the rule's script) |
| `qa-tool inject stop` | Deactivate the current rule |
| `qa-tool inject status` | Show the currently active rule |
| `qa-tool inject add` | Interactive wizard to create a new rule |
| `qa-tool inject remove <name>` | Delete a rule |

```bash
# List all rules
qa-tool inject list

# Activate a rule
qa-tool inject start payments_500

# Check what's active
qa-tool inject status

# Deactivate
qa-tool inject stop

# Add a new rule (full interactive wizard)
qa-tool inject add

# Remove a rule (prompts for confirmation)
qa-tool inject remove payments_500

# Remove without confirmation
qa-tool inject remove payments_500 --yes
```

---

### `qa-tool gui`

Launch the full Textual TUI. Recommended for interactive test sessions.

```bash
qa-tool gui
```

---

## GUI Overview

The GUI (`qa-tool gui`) is a retro neon arcade interface built with [Textual](https://textual.textualize.io/). All CLI features are available here via clickable buttons.

**Visual style:** Black background with neon palette — cyan borders and labels, magenta buttons and headers, yellow titles and warnings, green for active/running states, red for stop/error actions, gray for disabled controls.

```
╔════════════════════════════════════════════════════════════╗
║  ██╗  ██╗ ██████╗ ██╗      █████╗ ███████╗██╗     ██╗  ██╗ ║
║  ██║  ██║██╔═══██╗██║     ██╔══██╗██╔════╝██║     ╚██╗██╔╝ ║
║  ███████║██║   ██║██║     ███████║█████╗  ██║      ╚███╔╝  ║
║  ██╔══██║██║   ██║██║     ██╔══██║██╔══╝  ██║      ██╔██╗  ║
║  ██║  ██║╚██████╔╝███████╗██║  ██║██║     ███████╗██╔╝ ██╗ ║
║  ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝     ╚══════╝╚═╝  ╚═╝ ║
║                   QA NETWORK INTERCEPTOR                   ║
╚════════════════════════════════════════════════════════════╝

  SYSTEM STATUS
  ────────────────────────────────────────────────────────────
  MITMWEB    [ STOPPED ]   [START]  [STOP]
  EMULATOR   [ STOPPED ]   [PROXY ON]  [START]  [STOP]  [WIPE APP]  [WIPE DATA]
  CERT       [ NOT INSTALLED ]  [INSTALL]
  APK        [ NOT INSTALLED ]  [INSTALL]

  INJECTION RULES
  ────────────────────────────────────────────────────────────
  payments_500      POST /customer/checkout/v1/payments → 500    [START]
  esim_qr_kill      GET  /customer/v1/traveller/esims/{uuid}/qr  [START]

                                                          [+ ADD RULE]

  STATUS LOG
  ────────────────────────────────────────────────────────────
  [14:32:01] mitmweb started (PID 12345)
  [14:32:18] Emulator spawned (PID 23456)
  [14:33:44] Waiting for boot...
  [14:34:11] Emulator ready in 53.2s
```

### SYSTEM STATUS section

| Row | Buttons | Notes |
|-----|---------|-------|
| **MITMWEB** | START / STOP | Status pill turns green when running. |
| **EMULATOR** | PROXY ON/NO PROXY toggle · START / STOP / WIPE APP / WIPE DATA | Toggle is cyan when proxy is on, yellow when bypassed. WIPE DATA asks for confirmation. |
| **CERT** | INSTALL | Grayed out when emulator is not running. Queries the device via `adb` to verify the cert is actually present (not just a local file check). |
| **APK** | INSTALL / UNINSTALL | Toggles based on whether the package is detected on the device. Opens a picker modal when multiple APKs are in `apks/`. |

**Button color conventions:**

- Green — service is active / app is installed
- Red — action will stop or remove something
- Cyan — primary action is available
- Gray — action is not available (dependency not met)

### INJECTION RULES section

One row per rule in `rules/injection_rules.toml`. Each row shows the rule name, method, endpoint, and action type.

- **[START]** activates the rule (restarts mitmweb with the injection script attached). The row turns green and shows a `●` marker while active.
- **[STOP]** appears on the active row. Deactivates injection and restarts mitmweb cleanly.
- **[+ ADD RULE]** opens a minimal modal form: enter an endpoint and a status code, then click SAVE. The name is auto-generated from the last path segment + status code. The new rule appears in the list immediately.

### STATUS LOG section

Timestamped output of every action taken in the GUI. Scrollable. Shows the same information as the equivalent CLI commands.

---

## Injection Rules

### Rules file

Rules live in `rules/injection_rules.toml` at the project root. You can edit this file in any text editor. Changes take effect the next time you activate a rule.

### Rule format

```toml
[[rule]]
name        = "payments_500"
description = "Session creation returns HTTP 500"
endpoint    = "/customer/checkout/v1/payments"
action      = "respond"
method      = "POST"
status      = 500
body        = '{"error": "Internal Server Error"}'

[[rule]]
name        = "install_server_error"
description = "eSIM install returns 401 Unauthorized"
endpoint    = "/customer/v1/traveller/esims/{uuid}"
action      = "respond"
method      = "GET"
status      = 401
body        = '{"error": "Unauthorized"}'

[[rule]]
name        = "esim_qr_kill"
description = "Drop QR fetch connection"
endpoint    = "/customer/v1/traveller/esims/{uuid}/qr"
action      = "kill"
method      = "GET"
status      = 500
body        = ""
```

### Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Unique identifier used with `inject start <name>` |
| `description` | Yes | Human-readable label shown in the CLI and GUI |
| `endpoint` | Yes | URL path pattern (supports glob placeholders, see below) |
| `action` | Yes | `"respond"` — return a fake response; `"kill"` — drop the connection |
| `method` | No | `"GET"`, `"POST"`, `"PUT"`, etc. Leave empty (`""`) to match any method |
| `status` | For `respond` | HTTP status code to return (e.g. `500`, `401`, `503`) |
| `body` | For `respond` | Response body string, typically JSON. Leave empty for `kill` rules |

### Endpoint glob placeholders

Write friendly patterns; the tool converts them to regex internally.

| Placeholder | Matches |
|-------------|---------|
| `{uuid}` | UUID format: `a1b2c3d4-e5f6-...` |
| `{id}` | Numeric ID: `12345` |
| `{*}` | Any single path segment (no slashes) |
| `{**}` | Anything including slashes |

Everything else is treated as a literal string. Rules match using `re.search` (no `^` anchor), so the pattern only needs to appear somewhere in the URL path.

Examples:

```toml
endpoint = "/customer/v1/traveller/esims/{uuid}/qr"   # matches any eSIM UUID
endpoint = "/orders/{id}/items"                        # matches any numeric order ID
endpoint = "/api/v1/{*}/status"                        # matches any single segment
endpoint = "/api/{**}"                                 # matches anything under /api/
```

### Quick rule creation

Via the CLI wizard (full control):

```bash
qa-tool inject add
```

Via the GUI: click **[+ ADD RULE]** and enter the endpoint and status code.

Via direct file edit: add a `[[rule]]` block to `rules/injection_rules.toml` and run `qa-tool inject list` to verify it loaded.

---

## Runtime State

The tool stores ephemeral state in `~/.holafly-qa/`. You should never need to edit these, but they are useful for debugging:

| File | Purpose |
|------|---------|
| `config.toml` | Your AVD name and proxy port |
| `mitmweb.pid` | PID of the running mitmweb process |
| `emulator.pid` | PID of the running emulator process |
| `active_injection.txt` | Name of the currently active injection rule |
| `current_injection.py` | Auto-generated mitmproxy addon script |
| `mitmweb.log` | mitmweb stdout/stderr |
| `emulator.log` | Emulator stdout/stderr |

User-facing files you interact with directly:

| Path | Purpose |
|------|---------|
| `apks/` | Drop Codemagic APK builds here |
| `rules/injection_rules.toml` | Add and edit injection rules here |

---

## Known Limitations

**Adyen payments require `--no-proxy`**
The Adyen Drop-in SDK has certificate pinning. When mitmproxy is intercepting traffic, Adyen payment flows fail at the SDK level. Use `emulator start --no-proxy` (CLI) or the **NO PROXY** toggle (GUI) when testing payment screens. All non-payment flows are unaffected.

**Cert install requires a `google_apis` emulator image**
`google_apis_playstore` images block `adb root`, which is required to remount `/system` as writable. Always use `google_apis` (non-Play Store) images. API 33 and API 35 are confirmed working.

**Cert is wiped by `emulator wipe-data`**
A factory reset removes the CA certificate. Run `qa-tool cert install` again after every `wipe-data`.

**Injection rules path is dev-install only**
`rules/injection_rules.toml` is resolved relative to the package source via `__file__`. This works for editable installs (`pipx install --editable .`). It will break if the package is installed into a site-packages directory without the project root present (e.g. a future PyPI release). This is a known issue not yet addressed.

**No cert uninstall command**
There is no `cert uninstall`. To remove the certificate, use `emulator wipe-data` to factory reset the device.

---

## Architecture

The codebase follows a strict three-layer separation:

```
services/     All logic. Never prints. Returns structured data or raises exceptions.
commands/     Thin CLI wrappers. Parse args, call services, format output with typer.echo.
gui/app.py    Textual TUI. Calls the same service functions as the CLI. No duplicated logic.
```

When adding a feature: implement the service function first, then the CLI command, then the GUI integration. See `CLAUDE.md` for detailed architecture notes and hard-won debugging knowledge.
