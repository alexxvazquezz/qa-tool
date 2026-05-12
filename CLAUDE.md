# Holafly QA Tool — Context for Claude Code

You are working on a Python CLI + TUI tool for QA engineers at Holafly. It automates network interception testing of a Flutter-based eSIM app via mitmproxy, Android emulator, and failure injection rules.

## Project Location

`qa_tool/`

## What's Built (Working End-to-End)

The core tool is functional. A QA engineer can:

1. `qa-tool init` — pick an Android Virtual Device, creates config + `apks/` folder
2. `qa-tool doctor` — verifies adb, emulator, mitmweb, python are installed
3. `qa-tool mitmweb start/stop` — runs mitmproxy in the background with Adyen cert-pinning bypass (`--set ignore_hosts=".*adyen.*"`)
4. `qa-tool emulator start/stop/wipe-app/wipe-data` — runs the Android emulator with critical flags (`-http-proxy` at QEMU level, `-writable-system`, `-gpu host`). Has `--no-proxy` flag for testing Adyen payments that conflict with interception.
5. `qa-tool cert install` — pushes mitmproxy CA cert to `/system/etc/security/cacerts/` with remount-reboot handling
6. `qa-tool apk install` — installs APK from `apks/` folder, handles multi-APK selection via interactive picker
7. `qa-tool inject list/start/stop/status/add/remove` — manage failure injection rules
8. `qa-tool gui` — Textual TUI that wraps everything, retro neon arcade aesthetic

GUI features:
- Clickable buttons with color-coded status (green=active, red=stop/uninstall, yellow=pending, gray=disabled)
- Status log showing timestamped action output
- PROXY ON / NO PROXY toggle for emulator (cyan when on, yellow when off)
- APK button toggles INSTALL ↔ UNINSTALL based on device state
- APK version label below APK row — shows installed `versionName` from device + available APK filename
- CERT and APK status checks query the running emulator via adb (not just local file existence)
- Injection rule rows toggle START ↔ STOP with green active marker
- APK picker modal for multi-APK selection (Textual ModalScreen + ListView)
- Throttle preset row with clickable buttons (FULL, LTE, HSDPA, UMTS, EDGE, GSM) — cyan = active
- All long-running actions use `@work(thread=True)` so UI never freezes

## Full Directory Structure

/home/king/Code/qa_tool/
├── CLAUDE.md                         # This file
├── README.md
├── pyproject.toml                    # Package: holafly-qa, command: qa-tool
├── apks/                             # Drop Codemagic APKs here (visible, project root)
├── rules/                            # Injection rules (visible, project root)
│   └── injection_rules.toml          # THE editable rules file
├── src/
│   └── holafly_qa/
│       ├── init.py               # version = "0.1.0"
│       ├── main.py                   # Typer root app, registers all subcommands
│       ├── services/                 # ALL LOGIC LIVES HERE — never prints
│       │   ├── init.py
│       │   ├── checks.py             # CheckResult, check_command_exists, check_python_version, run_all_checks
│       │   ├── config.py             # Config dataclass, load/save ~/.holafly-qa/config.toml
│       │   ├── process.py            # PID file helpers, is_process_running (signal 0)
│       │   ├── avd.py                # list_avds via subprocess
│       │   ├── mitmweb.py            # start/stop/is_running, _collect_addon_scripts (injection + throttle)
│       │   ├── emulator.py           # start/stop/wait_for_boot/wipe_app/wipe_data
│       │   ├── cert.py               # install_cert orchestrator, CertError
│       │   ├── apk.py                # find_apks, pick_apk, install_apk, uninstall_app, ApkError
│       │   ├── injection.py          # InjectionRule, glob_to_regex, load/save rules, render_script, start/stop injection, add_rule, remove_rule, get_rule
│       │   └── throttle.py           # THROTTLE_PRESETS, render_throttle_script, get_active_throttle, set_throttle, clear_throttle
│       ├── commands/                  # THIN CLI WRAPPERS — parse args, call services, print output
│       │   ├── init.py
│       │   ├── doctor_cmd.py
│       │   ├── init_cmd.py
│       │   ├── mitmweb_cmd.py         # start, stop, throttle subcommands
│       │   ├── emulator_cmd.py
│       │   ├── cert_cmd.py
│       │   ├── apk_cmd.py
│       │   ├── inject_cmd.py          # list, start, stop, status, add (wizard), remove
│       │   └── gui_cmd.py
│       └── gui/
│           ├── init.py
│           └── app.py                # Textual app — calls services directly
└── tests/
└── test_main.py

## Architecture Rule — STRICT Service/Command/GUI Separation

**This is the most important convention. Do not violate it.**

- **Services** (`services/`) contain ALL logic. They NEVER print, NEVER call `typer.echo`, NEVER interact with the terminal. They return structured data or raise exceptions.
- **Commands** (`commands/`) are thin wrappers: parse CLI args, call services, format output with `typer.echo` and `typer.style`.
- **GUI** (`gui/app.py`) calls the same service functions as the CLI. No duplicated logic.

When adding a new feature: write the service function FIRST, then add the CLI wrapper, then add the GUI integration.

## Runtime State Locations

| Path | Purpose | User-facing? |
|------|---------|--------------|
| `~/.holafly-qa/config.toml` | User preferences (AVD name, port) | Rarely edited |
| `~/.holafly-qa/mitmweb.pid` | Tracks running mitmweb PID | Never edited |
| `~/.holafly-qa/emulator.pid` | Tracks running emulator PID | Never edited |
| `~/.holafly-qa/active_injection.txt` | Currently active rule name | Never edited |
| `~/.holafly-qa/current_injection.py` | Auto-generated mitmproxy addon script | Never edited |
| `~/.holafly-qa/active_throttle.txt` | Currently active throttle preset name | Never edited |
| `~/.holafly-qa/current_throttle.py` | Auto-generated mitmproxy throttle addon script | Never edited |
| `~/.holafly-qa/mitmweb.log` | mitmweb stdout/stderr | Debug only |
| `~/.holafly-qa/emulator.log` | emulator stdout/stderr | Debug only |
| `~/.holafly-qa/cert_hash.txt` | Cached cert subject hash | Never edited |
| `~/.holafly-qa/<hash>.0` | Cached hashed cert file for push | Never edited |
| `<project-root>/apks/` | APK files for install | **User drops files here** |
| `<project-root>/rules/injection_rules.toml` | Injection rules | **User edits this freely** |

The split is intentional: ephemeral runtime state in the hidden home dir, user-facing editable data in the visible project root.

## Injection Rules System

### Rules File Format

Located at `<project-root>/rules/injection_rules.toml`. Users can edit this directly in any text editor.

```toml
[[rule]]
name = "payments_500"
description = "Session creation returns HTTP 500"
endpoint = "/customer/checkout/v1/payments"
action = "respond"
method = "POST"
status = 500
body = '{"error": "Internal Server Error"}'

[[rule]]
name = "esim_qr_kill"
description = "Drop QR fetch connection"
endpoint = "/customer/v1/traveller/esims/{uuid}/qr"
action = "kill"
method = "GET"
status = 500
body = ""
```

### Glob Placeholders in `endpoint`

Users write friendly patterns. The `glob_to_regex()` function converts them to regex internally.

- `{uuid}` → `[a-f0-9\-]+` (matches UUIDs)
- `{id}` → `\d+` (matches numeric IDs)
- `{*}` → `[^/]+` (any single path segment)
- `{**}` → `.+` (anything including slashes)

Everything else is `re.escape()`d as a literal. `$` anchor appended at end. No `^` anchor (mitmproxy uses `re.search`).

### InjectionRule Dataclass

```python
@dataclass
class InjectionRule:
    name: str          # unique identifier, used by CLI "inject start <name>"
    description: str   # human-readable label
    endpoint: str      # glob pattern like /customer/.../esims/{uuid}/qr
    action: str        # "respond" or "kill"
    method: str = ""   # HTTP method filter, empty = any
    status: int = 500  # only used for action="respond"
    body: str = ""     # only used for action="respond"
```

This dataclass shape is designed so a future GUI form binds directly to its fields.

### How Injection Activation Works

1. User runs `qa-tool inject start <name>` or clicks START in GUI
2. `start_injection(name)` looks up the rule in the TOML file
3. `render_script(rule)` generates a valid mitmproxy addon Python script
4. Script is written to `~/.holafly-qa/current_injection.py`
5. Running mitmweb is stopped and restarted with `-s <script_path>`
6. Rule name is written to `~/.holafly-qa/active_injection.txt`
7. `stop_injection()` reverses this: restarts mitmweb without `-s`, deletes state file

### RULES_FILE Path Resolution

```python
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
RULES_FILE = _PROJECT_ROOT / "rules" / "injection_rules.toml"
```

Uses `__file__`-based resolution. Works in dev mode (editable install). Will break for remote pipx installs — flagged as known distribution issue, not yet addressed.

## Throttle System

### How Throttle Activation Works

1. User runs `qa-tool mitmweb throttle <preset>` or clicks a preset button in the GUI
2. `set_throttle(preset)` in `services/throttle.py` generates a mitmproxy addon Python script
3. Script is written to `~/.holafly-qa/current_throttle.py`
4. Preset name is written to `~/.holafly-qa/active_throttle.txt`
5. If mitmweb is running, it is stopped and restarted (picks up the new script via `_collect_addon_scripts()`)
6. `clear_throttle()` / preset `"full"` deletes both state files and restarts mitmweb

### Multi-Script mitmweb

`_collect_addon_scripts()` in `services/mitmweb.py` checks both state files and returns all active script paths. `start_mitmweb()` passes each as a separate `-s <path>` argument. Injection and throttle can run simultaneously with no conflicts.

## Config Dataclass

```python
@dataclass
class Config:
    avd_name: str = ""
    mitm_port: int = 8080
    apk_dir: str = str(Path.home() / "Downloads")
```

Stored at `~/.holafly-qa/config.toml`. Read with `tomllib`, written with `tomli_w`. Uses `.get()` with defaults for forward compatibility.

## Known Quirks / Hard-Won Knowledge

These came from hours of debugging. Do not re-discover them.

### Emulator / Proxy
- **Flutter's Dart HttpClient bypasses Android system proxy settings.** `adb shell settings put global http_proxy` does NOT work. Must use `-http-proxy` flag at QEMU level (emulator launch flag).
- **Adyen SDK has certificate pinning.** mitmproxy MUST launch with `--set ignore_hosts=".*adyen.*"` or the Adyen Drop-in SDK breaks entirely.
- **`-writable-system` is required** for cert install. The emulator must boot with this flag.
- **`-gpu host` is the correct default.** It's fast. `swiftshader_indirect` is slow and makes the emulator unusable on this machine. Only fall back if hardware doesn't support it.
- **`-no-snapshot` prevents disk bloat.** Emulator snapshots consume 2-8 GB each. We use `-no-snapshot` (no load, no save) to prevent accumulation.
- **Default emulator flags:** `-gpu host -cores 4 -memory 4096 -writable-system -no-snapshot`

### Emulator Image Compatibility
- **`google_apis_playstore` images disable `adb root`.** Cert install cannot work on Play Store images. QA must use `google_apis` (non-playstore) images.
- **API 33 is documented as fully compatible.** API 35 has been tested and works. API 34 is theoretically risky (APEX conscrypt store change) but untested. The version restriction was removed — don't add it back without evidence.

### Cert Install
- **`adb remount` may fail the first time** and require a reboot cycle. The code handles this: parses remount output, reboots if needed, runs remount again.
- **Use `openssl x509 -subject_hash_old` NOT `-subject_hash`.** Android uses the old hash algorithm for cert filenames.
- **Cert check in GUI queries the device** via `adb shell ls /system/etc/security/cacerts/` and looks for the expected hash filename. Not just a local file existence check.

### APK Management
- **APK folder lives at project root:** `<project-root>/apks/`
- **Path resolved via `__file__`:** same pattern as rules folder
- **Multi-APK handling:** if 1 APK exists, auto-install. If multiple, show picker (questionary for CLI, Textual ModalScreen for GUI). If 0, error.
- **APK state check in GUI:** queries `adb shell pm list packages <name>` to determine if app is installed on device
- **APK version label:** `_get_installed_version()` in `app.py` runs `adb shell dumpsys package <pkg>` and parses `versionName=` line. `get_apk_display_info()` combines this with the available APK filename for the label below the APK row.
- **Default package name:** `com.holafly.holafly.dev`

### Process Management
- Every background process (mitmweb, emulator) spawned with `subprocess.Popen(..., start_new_session=True, stdin=DEVNULL, stdout=log_file, stderr=STDOUT)`
- Stop logic is multi-phase: emulator uses `adb emu kill` (graceful) → SIGTERM → SIGKILL with polling. mitmweb uses SIGTERM → SIGKILL.
- PID files at `~/.holafly-qa/<name>.pid` track running processes across CLI invocations
- `is_process_running(pid)` uses `os.kill(pid, 0)` — signal 0 idiom

### GUI Specifics
- **Do NOT name any method `log` on the App class.** Textual uses `self.log` internally. Our method is `add_log`.
- **Workers use `@work(thread=True, exclusive=True)`** for all service calls. Never call blocking service functions on the main thread.
- **`self.call_from_thread(self.add_log, "message")` from workers** — thread-safe way to update UI from background threads.
- **`self.call_from_thread(self.refresh_all)` after every worker** to update all row colors/states.
- **Button IDs follow a convention:** `btn-{system_id}-{primary|secondary|tertiary}` for system rows, `rule-btn-{rule_name}` for rule rows, `btn-proxy-toggle` for the proxy toggle, `btn-apk-primary` for APK install/uninstall, `btn-throttle-{preset}` for throttle preset buttons.
- **`#apk-version-label`** is a `Label` below the APK SystemRow, updated in `refresh_all()` via `get_apk_display_info()`. Shows installed versionName + available APK filename.

## Dependencies

In `pyproject.toml`:
```toml
dependencies = [
    "typer>=0.12.0",
    "tomli-w>=1.0.0",
    "questionary>=2.0.0",
    "textual>=0.80.0",
]
```

`tomllib` is built into Python 3.11+. No extra dependency needed for TOML reading.

## What's NOT Built (Do Not Add Unless Asked)

These were explicitly scoped out by the user:

- **Cert uninstall** — users wipe the emulator instead. Too much code for marginal value.
- **API 34+ APEX conscrypt support** — not needed based on current testing.
- **Unit tests** — user explicitly declined. Manual end-to-end testing is the workflow.
- **Git integration** — no repo set up yet. User will add when company repo is available.

## Current Tasks for Claude Code

### Task 1: Easy Rule Creation (CLI + GUI)

**Problem:** The existing `qa-tool inject add` wizard asks too many questions. Users just want to enter an endpoint and an error code.

**New CLI command: `qa-tool inject quick <endpoint> <status>`**

Example:
```bash
qa-tool inject quick /customer/checkout/v1/payments 500
```

Auto-generates:
- `name`: derived from last path segment + status (e.g. `payments_500`). If name collides, append `_2`, `_3`, etc.
- `description`: auto-generated (e.g. `"/customer/checkout/v1/payments → 500"`)
- `action`: `"respond"` (default for status code responses)
- `method`: `""` (any method) — user can override with `--method POST`
- `body`: `'{"error": "Internal Server Error"}'` — user can override with `--body '{...}'`

Keep the existing verbose `qa-tool inject add` wizard for power users who want full control.

**New service function:** `quick_add_rule(endpoint: str, status: int, method: str = "", body: str = "") -> InjectionRule` in `services/injection.py`. Handles:
- Name auto-generation from endpoint (extract last meaningful path segment, append status)
- Duplicate name avoidance (append `_2`, `_3`, etc.)
- Validation (endpoint must start with `/`, status must be a valid HTTP code)
- Calls `add_rule()` internally to persist

Both CLI and GUI must call this same service function.

**New GUI modal:** Add an `[+ ADD RULE]` button at the bottom of the INJECTION RULES section. Clicking opens a minimal Textual ModalScreen form with:
- Endpoint text input (required, must start with `/`)
- Status code input (defaults to 500)
- `[SAVE]` and `[CANCEL]` buttons

On Save: call `quick_add_rule()`, dismiss modal, refresh rules list so the new rule appears immediately. Match the neon arcade aesthetic (cyan borders, magenta buttons, yellow titles).

### Task 2: Network Speed Throttling ✓ DONE

**Implemented via mitmproxy addon scripts** (not `-netspeed` emulator flag — that approach was abandoned because it requires an emulator restart to change).

**How it works:** `services/throttle.py` generates a mitmproxy addon script that delays each response by base latency + body-size/bandwidth. The script is written to `~/.holafly-qa/current_throttle.py`. mitmweb auto-detects and loads it on start via `_collect_addon_scripts()` in `services/mitmweb.py`.

**CLI:** `qa-tool mitmweb throttle <preset>` — restarts mitmweb with the new script if it's running, or saves the setting for the next start.

**GUI:** Throttle row with preset buttons (FULL, LTE, HSDPA, UMTS, EDGE, GSM). Active preset is cyan, others are dark gray. Handled in `refresh_throttle_buttons()` and `worker_set_throttle()`.

**Presets defined in `THROTTLE_PRESETS`:**
- `full` — no throttling (None, clears the script)
- `lte` — 58,000 kbps / 50ms latency
- `hsdpa` — 14,400 kbps / 100ms latency
- `umts` — 1,920 kbps / 200ms latency (3G)
- `edge` — 118 kbps / 400ms latency
- `gsm` — 9.6 kbps / 750ms latency

**Throttle + injection coexist:** Both scripts can be active simultaneously. `_collect_addon_scripts()` returns both if both state files exist; mitmweb loads each with a separate `-s` flag.

### Task 3 (Optional): Auto-Refresh in GUI

Add a 3-second interval timer that calls `refresh_all()`. Use Textual's `set_interval()`.

**Caution:** `get_cert_state()` and `get_apk_state()` each make adb calls (~500ms). If auto-refresh feels sluggish, either increase the interval to 5 seconds or skip adb-based checks on the timer (only refresh them on button actions).

### Task 4 (Optional): README.md

Write a real README for the project covering:
- What the tool does (one paragraph)
- Install instructions (`pipx install --editable .` for dev, `pip install -e ".[dev]"` for venv)
- Quick start (init → doctor → mitmweb start → emulator start → cert install → apk install)
- All CLI commands with examples
- GUI launch (`qa-tool gui`)
- Injection rules format with examples
- Known limitations
- Architecture overview (for contributors)

## Code Style Conventions

- **Type hints everywhere.** `list[str]`, `int | None`, `Path | None` (Python 3.10+ syntax).
- **Docstrings on all public functions.** Explain purpose, args, returns, raises.
- **Custom exceptions per service module.** `CertError`, `ApkError`, etc. CLI/GUI catches these and shows colored messages.
- **`typer.style()` for colored CLI output.** Green ✓ for success, red ✗ for errors, yellow for warnings.
- **PID file pattern** for any new background process. Reuse `services/process.py` helpers.
- **No relative imports.** Always `from holafly_qa.services.X import Y`.
- **Background work in GUI uses `@work(thread=True, exclusive=True)`.** Call `self.call_from_thread(self.add_log, "...")` from workers.
- **GUI CSS uses neon arcade palette:** `#0a0a0a` (background), `#00ffff` (cyan, borders/labels), `#ff00ff` (magenta, buttons/headers), `#ffff00` (yellow, titles/warnings), `#00ff00` (green, success/active), `#ff0040` (red, stop/error), `#666666` (gray, disabled).

## Verification Checklist

Before committing any changes:

1. `python3 -c "from holafly_qa.main import app; print('OK')"` — imports cleanly
2. `qa-tool --help` — all commands listed
3. `qa-tool inject list` — rules load from `rules/injection_rules.toml`
4. `qa-tool gui` — opens without error, all sections visible, buttons responsive
5. Test the specific feature you changed end-to-end
