"""Main Textual app for the Holafly QA console."""

from datetime import datetime
import subprocess

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Label, ListItem, ListView, Static

from holafly_qa.services.apk import find_apks_in_dir, install_apk, pick_apk, uninstall_app
from holafly_qa.services.cert import CertError, MITM_CERT_PATH, install_cert
from holafly_qa.services.config import load_config
from holafly_qa.services.emulator import (
    is_emulator_running,
    start_emulator,
    stop_emulator,
    wait_for_boot,
    wipe_emulator_data,
)
from holafly_qa.services.injection import (
    get_active_injection,
    load_rules,
    start_injection,
    stop_injection,
)
from holafly_qa.services.mitmweb import (
    is_mitmweb_running,
    start_mitmweb,
    stop_mitmweb,
)


HOLAFLY_PACKAGE = "com.holafly.holafly.dev"


def get_mitmweb_state() -> str:
    return "ONLINE" if is_mitmweb_running() else "OFFLINE"


def get_emulator_state() -> str:
    return "ONLINE" if is_emulator_running() else "OFFLINE"

def _is_cert_on_device() -> bool:
    """Check if any mitmproxy cert is installed on the running emulator."""
    try:
        result = subprocess.run(
            ["adb", "shell", "ls", "/system/etc/security/cacerts/"],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False

    if result.returncode != 0:
        return False

    # Our cert files are named like "c8750f0d.0" — short hex hash + .0
    # Standard Android certs also have this format, so we check for any
    # file that was added recently by looking for cert files in general.
    # Simple heuristic: if the count is higher than a fresh wipe baseline,
    # something was added. More reliably: check for our specific hash file.
    files = result.stdout.split()

    # Read the local cert hash to know what filename to look for
    from holafly_qa.services.cert import (
        CACHED_CERT_DIR,
        HASH_RECORD_FILE,
    )

    if not HASH_RECORD_FILE.exists():
        # We've never pushed a cert, so definitely not installed
        return False

    expected_hash = HASH_RECORD_FILE.read_text().strip()
    expected_filename = f"{expected_hash}.0"

    return expected_filename in files


def _is_apk_on_device() -> bool:
    """Check if the Holafly package is installed on the running emulator."""
    try:
        result = subprocess.run(
            ["adb", "shell", "pm", "list", "packages", HOLAFLY_PACKAGE],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False

    if result.returncode != 0:
        return False

    return f"package:{HOLAFLY_PACKAGE}" in result.stdout


def get_cert_state() -> str:
    """Return the cert installation state on the running emulator."""
    if not is_emulator_running():
        return "NO DEVICE"
    if _is_cert_on_device():
        return "INSTALLED"
    return "NOT INSTALLED"


def get_apk_state() -> str:
    """Return the APK installation state on the running emulator."""
    if not is_emulator_running():
        return "NO DEVICE"
    if _is_apk_on_device():
        return "INSTALLED"
    return "NOT INSTALLED"


class SystemRow(Horizontal):
    def __init__(
        self,
        system_id: str,
        display_name: str,
        state_fn,
        primary_label: str,
        secondary_label: str = "",
        tertiary_label: str = "",
    ) -> None:
        super().__init__(classes="system-row")
        self.system_id = system_id
        self.display_name = display_name
        self.state_fn = state_fn
        self.primary_label = primary_label
        self.secondary_label = secondary_label
        self.tertiary_label = tertiary_label

    def compose(self) -> ComposeResult:
        yield Label("●", classes="indicator", id=f"ind-{self.system_id}")
        yield Label(f"{self.display_name:<10}", classes="system-name")
        yield Label(
            "[ ........ ]",
            classes="status-pill",
            id=f"pill-{self.system_id}",
        )
        yield Button(
            self.primary_label,
            classes="action-btn",
            id=f"btn-{self.system_id}-primary",
        )
        if self.secondary_label:
            yield Button(
                self.secondary_label,
                classes="action-btn",
                id=f"btn-{self.system_id}-secondary",
            )
        if self.tertiary_label:
            yield Button(
                self.tertiary_label,
                classes="action-btn",
                id=f"btn-{self.system_id}-tertiary",
            )

    def refresh_state(self) -> None:
        state = self.state_fn()
        indicator = self.query_one(f"#ind-{self.system_id}", Label)
        pill = self.query_one(f"#pill-{self.system_id}", Label)

        pill.update(f"[ {state:^12} ]")

        is_active = state in ("ONLINE", "INSTALLED")

        if is_active:
            indicator.styles.color = "#00ff00"
            pill.styles.color = "#00ff00"
        elif state == "MISSING":
            indicator.styles.color = "#ff0000"
            pill.styles.color = "#ff0000"
        else:
            indicator.styles.color = "#666666"
            pill.styles.color = "#ffff00"

        primary_btn = self.query_one(
            f"#btn-{self.system_id}-primary", Button
        )

        if self.system_id in ("mitmweb", "emulator"):
            if is_active:
                primary_btn.styles.background = "#666666"
                primary_btn.disabled = True
                if self.secondary_label:
                    sec = self.query_one(
                        f"#btn-{self.system_id}-secondary", Button
                    )
                    sec.styles.background = "#ff0040"
                    sec.disabled = False
            else:
                primary_btn.styles.background = "#00ff00"
                primary_btn.disabled = False
                if self.secondary_label:
                    sec = self.query_one(
                        f"#btn-{self.system_id}-secondary", Button
                    )
                    sec.styles.background = "#666666"
                    sec.disabled = True

        elif self.system_id == "apk":
            if state == "INSTALLED":
                primary_btn.label = "UNINSTALL"
                primary_btn.styles.background = "#ff0040"
            else:
                primary_btn.label = "INSTALL"
                primary_btn.styles.background = "#00ff00"


class RuleRow(Horizontal):
    def __init__(self, name: str, summary: str) -> None:
        super().__init__(classes="rule-row")
        self.rule_name = name
        self.summary = summary
        self.is_active = False

    def compose(self) -> ComposeResult:
        yield Label(
            f"  {self.rule_name:<18}",
            classes="rule-name",
            id=f"name-{self.rule_name}",
        )
        yield Label(self.summary, classes="rule-summary")
        yield Button(
            "START",
            classes="action-btn",
            id=f"rule-btn-{self.rule_name}",
        )

    def set_active(self, active: bool) -> None:
        self.is_active = active
        name_label = self.query_one(f"#name-{self.rule_name}", Label)
        btn = self.query_one(f"#rule-btn-{self.rule_name}", Button)

        if active:
            name_label.update(f"► {self.rule_name:<18}")
            name_label.styles.color = "#00ff00"
            btn.label = "STOP"
            btn.styles.background = "#ff0040"
        else:
            name_label.update(f"  {self.rule_name:<18}")
            name_label.styles.color = "#00ffff"
            btn.label = "START"
            btn.styles.background = "#ff00ff"

class ApkPickerScreen(ModalScreen):
    """Modal picker for selecting one APK when multiple are available."""

    CSS = """
    ApkPickerScreen {
        align: center middle;
    }

    #picker-container {
        width: 70;
        height: auto;
        max-height: 24;
        border: heavy #00ffff;
        background: #0a0a0a;
        padding: 1 2;
    }

    #picker-title {
        color: #ffff00;
        text-style: bold;
        content-align: center middle;
        height: 1;
        margin-bottom: 1;
    }

    #picker-hint {
        color: #666666;
        content-align: center middle;
        height: 1;
        margin-top: 1;
    }

    ListView {
        background: #0a0a0a;
        border: none;
        height: auto;
        max-height: 16;
    }

    ListItem {
        background: #0a0a0a;
        color: #00ffff;
        padding: 0 1;
    }

    ListItem:hover {
        background: #ff00ff;
        color: #0a0a0a;
    }

    ListItem.--highlight {
        background: #ff00ff;
        color: #0a0a0a;
        text-style: bold;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, apk_paths: list) -> None:
        super().__init__()
        self.apk_paths = apk_paths

    def compose(self) -> ComposeResult:
        with Container(id="picker-container"):
            yield Label("◆ SELECT APK ◆", id="picker-title")
            yield ListView(
                *[ListItem(Label(p.name)) for p in self.apk_paths],
                id="apk-list",
            )
            yield Label("↑↓ navigate   ENTER select   ESC cancel", id="picker-hint")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """User pressed Enter or clicked an item."""
        index = event.list_view.index
        if index is not None:
            self.dismiss(self.apk_paths[index])

    def action_cancel(self) -> None:
        """User pressed Escape."""
        self.dismiss(None)


class HolaflyQAApp(App):
    """Holafly QA Console — neon arcade TUI for proxy testing."""

    TITLE = "HOLAFLY QA CONSOLE"
    SUB_TITLE = "▓▓▓ READY ▓▓▓"

    CSS = """
    Screen { background: #0a0a0a; }
    Header { background: #ff00ff; color: #0a0a0a; text-style: bold; }
    Footer { background: #ff00ff; color: #0a0a0a; }
    .section {
        border: heavy #00ffff;
        background: #0a0a0a;
        margin: 1 2;
        padding: 1 2;
        height: auto;
    }
    .section-title {
        color: #ffff00;
        text-style: bold;
        margin-bottom: 1;
    }
    .system-row, .rule-row {
        height: 3;
        align: left middle;
        padding: 0 1;
    }
    .indicator {
        color: #00ff00;
        text-style: bold;
        width: 3;
    }
    .system-name {
        color: #00ffff;
        text-style: bold;
        width: 12;
    }
    .status-pill {
        color: #ffff00;
        width: 18;
    }
    .rule-name {
        color: #00ffff;
        text-style: bold;
        width: 22;
    }
    .rule-summary {
        color: #ffffff;
        width: 1fr;
    }
    .action-btn {
        background: #ff00ff;
        color: #0a0a0a;
        border: none;
        margin: 0 1;
        min-width: 12;
        height: 1;
    }
    .action-btn:hover {
        background: #ffff00;
        color: #0a0a0a;
    }
    .system-row-with-toggle {
        height: 3;
        align: left middle;
        padding: 0 1;
    }

    .proxy-toggle-on {
        background: #00ffff;
        color: #0a0a0a;
        text-style: bold;
    }

    .proxy-toggle-off {
        background: #ffff00;
        color: #0a0a0a;
        text-style: bold;
    }
    #log-section {
        height: 14;
    }
    #log-content {
        color: #00ff00;
        background: #0a0a0a;
        padding: 0 1;
    }
    #active-row {
        height: 3;
        align: left middle;
        padding: 0 1;
        color: #ff00ff;
        text-style: bold;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.log_lines: list[str] = []
        self.use_proxy: bool = True  # Resets to True on every GUI launch

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Vertical():
            with Container(classes="section"):
                yield Label("◆ SYSTEMS ◆", classes="section-title")
                yield SystemRow(
                    "mitmweb", "MITMWEB", get_mitmweb_state, "START", "STOP"
                )
                with Horizontal(classes="system-row-with-toggle"):
                    yield SystemRow(
                        "emulator",
                        "EMULATOR",
                        get_emulator_state,
                        "START",
                        "STOP",
                        "WIPE",
                    )
                    yield Button(
                        "PROXY ON",
                        id="btn-proxy-toggle",
                        classes="action-btn proxy-toggle-on",
                    )
                yield SystemRow(
                    "cert", "CERT", get_cert_state, "INSTALL"
                )
                yield SystemRow(
                    "apk", "APK", get_apk_state, "INSTALL"
                )

            with Container(classes="section", id="rules-section"):
                yield Label("◆ INJECTION RULES ◆", classes="section-title")

            with Container(classes="section", id="log-section"):
                yield Label("◆ STATUS LOG ◆", classes="section-title")
                yield Static("> GUI initialized", id="log-content")

        yield Footer()

    def on_mount(self) -> None:
        rules_section = self.query_one("#rules-section", Container)
        rules = load_rules()
        if not rules:
            rules_section.mount(
                Static(
                    "  No rules defined. Run 'qa-tool inject add' from CLI.",
                    classes="rule-summary",
                )
            )
        else:
            for rule in rules:
                method = rule.method or "ANY"
                if rule.action == "respond":
                    summary = f"{method} {rule.endpoint} → {rule.status}"
                else:
                    summary = f"{method} {rule.endpoint} → kill"
                rules_section.mount(RuleRow(rule.name, summary))

        rules_section.mount(Label("Active: (none)", id="active-row"))
        self.refresh_all()

    def refresh_all(self) -> None:
        for row in self.query(SystemRow):
            row.refresh_state()

        active = get_active_injection()
        for row in self.query(RuleRow):
            row.set_active(row.rule_name == active)

        try:
            active_label = self.query_one("#active-row", Label)
            active_label.update(f"Active: {active or '(none)'}")
        except Exception:
            pass

    def add_log(self, message: str) -> None:
        """Append a line to the status log and re-render."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_lines.append(f"> [{timestamp}] {message}")
        self.log_lines = self.log_lines[-10:]
        log_widget = self.query_one("#log-content", Static)
        log_widget.update("\n".join(self.log_lines))

    def _toggle_proxy(self) -> None:
        """Flip proxy mode and update the toggle button visuals."""
        self.use_proxy = not self.use_proxy
        btn = self.query_one("#btn-proxy-toggle", Button)
        if self.use_proxy:
            btn.label = "PROXY ON"
            btn.remove_class("proxy-toggle-off")
            btn.add_class("proxy-toggle-on")
            self.add_log("Proxy mode: ON (default)")
        else:
            btn.label = "NO PROXY"
            btn.remove_class("proxy-toggle-on")
            btn.add_class("proxy-toggle-off")
            self.add_log("Proxy mode: OFF")

    def action_refresh(self) -> None:
        self.refresh_all()
        self.add_log("Status refreshed")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""

        if button_id == "btn-proxy-toggle":
            self._toggle_proxy()
            return
        if button_id == "btn-mitmweb-primary":
            self.worker_mitmweb_start()
        elif button_id == "btn-mitmweb-secondary":
            self.worker_mitmweb_stop()
        elif button_id == "btn-emulator-primary":
            self.worker_emulator_start()
        elif button_id == "btn-emulator-secondary":
            self.worker_emulator_stop()
        elif button_id == "btn-emulator-tertiary":
            self.worker_emulator_wipe()
        elif button_id == "btn-cert-primary":
            self.worker_cert_install()
        elif button_id == "btn-apk-primary":
            apk_btn = self.query_one("#btn-apk-primary", Button)
            if str(apk_btn.label) == "UNINSTALL":
                self.worker_apk_uninstall()
            else:
                self.worker_apk_install()
        elif button_id and button_id.startswith("rule-btn-"):
            rule_name = button_id.removeprefix("rule-btn-")
            self.worker_toggle_rule(rule_name)

    @work(thread=True, exclusive=True)
    def worker_mitmweb_start(self) -> None:
        self.call_from_thread(self.add_log, "Starting mitmweb...")
        try:
            pid = start_mitmweb()
            self.call_from_thread(self.add_log, f"✓ mitmweb started (PID {pid})")
        except Exception as e:
            self.call_from_thread(self.add_log, f"✗ mitmweb start failed: {e}")
        self.call_from_thread(self.refresh_all)

    @work(thread=True, exclusive=True)
    def worker_mitmweb_stop(self) -> None:
        self.call_from_thread(self.add_log, "Stopping mitmweb...")
        try:
            stop_mitmweb()
            self.call_from_thread(self.add_log, "✓ mitmweb stopped")
        except Exception as e:
            self.call_from_thread(self.add_log, f"✗ mitmweb stop failed: {e}")
        self.call_from_thread(self.refresh_all)

    @work(thread=True, exclusive=True)
    def worker_emulator_start(self) -> None:
        config = load_config()
        if not config.avd_name:
            self.call_from_thread(
                self.add_log, "✗ No AVD configured. Run 'qa-tool init'."
            )
            return
        proxy_msg = "with proxy" if self.use_proxy else "WITHOUT proxy"
        self.call_from_thread(
            self.add_log, f"Starting emulator ({config.avd_name}) {proxy_msg}..."
        )
        try:
            pid = start_emulator(
                avd_name=config.avd_name,
                proxy_port=config.mitm_port,
                use_proxy=self.use_proxy,
            )
            self.call_from_thread(
                self.add_log, f"Emulator spawned (PID {pid}), waiting for boot..."
            )
            booted = wait_for_boot(timeout=180)
            if booted:
                self.call_from_thread(self.add_log, "✓ Emulator ready")
            else:
                self.call_from_thread(self.add_log, "✗ Emulator boot timeout")
        except Exception as e:
            self.call_from_thread(self.add_log, f"✗ Emulator start failed: {e}")
        self.call_from_thread(self.refresh_all)

    @work(thread=True, exclusive=True)
    def worker_emulator_stop(self) -> None:
        self.call_from_thread(self.add_log, "Stopping emulator...")
        try:
            stop_emulator()
            self.call_from_thread(self.add_log, "✓ Emulator stopped")
        except Exception as e:
            self.call_from_thread(self.add_log, f"✗ Emulator stop failed: {e}")
        self.call_from_thread(self.refresh_all)

    @work(thread=True, exclusive=True)
    def worker_emulator_wipe(self) -> None:
        config = load_config()
        if not config.avd_name:
            self.call_from_thread(self.add_log, "✗ No AVD configured")
            return
        self.call_from_thread(
            self.add_log, "Wiping emulator (1-2 minutes)..."
        )
        try:
            pid = wipe_emulator_data(
                avd_name=config.avd_name,
                proxy_port=config.mitm_port,
                use_proxy=self.use_proxy,
            )
            self.call_from_thread(
                self.add_log,
                f"✓ Emulator wiped (PID {pid}). Cert is gone — reinstall if needed.",
            )
        except Exception as e:
            self.call_from_thread(self.add_log, f"✗ Wipe failed: {e}")
        self.call_from_thread(self.refresh_all)

    @work(thread=True, exclusive=True)
    def worker_cert_install(self) -> None:
        if not is_emulator_running():
            self.call_from_thread(
                self.add_log, "✗ Emulator must be running to install cert"
            )
            return
        self.call_from_thread(
            self.add_log, "Installing cert (2-3 minutes)..."
        )
        try:
            result = install_cert()
            self.call_from_thread(
                self.add_log,
                f"✓ Cert installed (hash {result['cert_hash']})",
            )
        except CertError as e:
            self.call_from_thread(self.add_log, f"✗ Cert install failed: {e}")
        except Exception as e:
            self.call_from_thread(self.add_log, f"✗ Unexpected error: {e}")
        self.call_from_thread(self.refresh_all)

    @work(thread=True, exclusive=True)
    def worker_apk_install(self) -> None:
        if not is_emulator_running():
            self.call_from_thread(
                self.add_log, "✗ Emulator must be running to install APK"
            )
            return

        apks = find_apks_in_dir()

        if not apks:
            self.call_from_thread(
                self.add_log, "✗ No APKs found in apks/ folder"
            )
            return

        if len(apks) == 1:
            self._install_apk_path(apks[0])
            return

        # Multiple APKs — show the picker modal
        self.call_from_thread(self._show_apk_picker, apks)

    def _show_apk_picker(self, apks: list) -> None:
        """Push the picker modal and continue install on selection."""
        def handle_pick(selected) -> None:
            if selected is None:
                self.add_log("APK selection cancelled")
                return
            # Install runs in a worker so it doesn't block the UI
            self._install_after_pick(selected)

        self.push_screen(ApkPickerScreen(apks), handle_pick)

    @work(thread=True, exclusive=True)
    def _install_after_pick(self, apk_path) -> None:
        self._install_apk_path(apk_path)

    def _install_apk_path(self, apk_path) -> None:
        """Shared install logic used by both single-apk and picker paths."""
        self.call_from_thread(
            self.add_log, f"Installing {apk_path.name}..."
        )
        try:
            install_apk(apk_path)
            self.call_from_thread(self.add_log, "✓ APK installed")
        except Exception as e:
            self.call_from_thread(self.add_log, f"✗ APK install failed: {e}")
        self.call_from_thread(self.refresh_all)

    @work(thread=True, exclusive=True)
    def worker_apk_uninstall(self) -> None:
        if not is_emulator_running():
            self.call_from_thread(
                self.add_log, "✗ Emulator must be running to uninstall APK"
            )
            return
        self.call_from_thread(
            self.add_log, f"Uninstalling {HOLAFLY_PACKAGE}..."
        )
        try:
            was_installed = uninstall_app(HOLAFLY_PACKAGE)
            if was_installed:
                self.call_from_thread(self.add_log, "✓ APK uninstalled")
            else:
                self.call_from_thread(
                    self.add_log, "App was not installed (nothing to do)"
                )
        except Exception as e:
            self.call_from_thread(self.add_log, f"✗ Uninstall failed: {e}")
        self.call_from_thread(self.refresh_all)

    @work(thread=True, exclusive=True)
    def worker_toggle_rule(self, rule_name: str) -> None:
        active = get_active_injection()
        if active == rule_name:
            self.call_from_thread(self.add_log, f"Stopping injection: {rule_name}")
            try:
                stop_injection()
                self.call_from_thread(self.add_log, "✓ Injection stopped")
            except Exception as e:
                self.call_from_thread(self.add_log, f"✗ Stop failed: {e}")
        else:
            self.call_from_thread(self.add_log, f"Activating rule: {rule_name}")
            try:
                rule = start_injection(rule_name)
                self.call_from_thread(self.add_log, f"✓ Injection active: {rule.name}")
            except Exception as e:
                self.call_from_thread(self.add_log, f"✗ Activation failed: {e}")
        self.call_from_thread(self.refresh_all)

def run() -> None:
    HolaflyQAApp().run()