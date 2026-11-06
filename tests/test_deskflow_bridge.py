"""无界面 deskflow-core 集成的检测、配置与进程管理测试。"""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

import deskflow_bridge


def touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    return path


def prepared(tmp: str, *, mode: str = "client") -> deskflow_bridge.PreparedDeskflow:
    root = Path(tmp)
    return deskflow_bridge.PreparedDeskflow(
        mode=mode,
        core_path=str(root / "deskflow-core"),
        settings_path=root / "Deskflow.conf",
        server_config_path=root / "Deskflow-server.conf" if mode == "server" else None,
        log_path=root / "deskflow.log",
        pid_path=root / "deskflow.pid",
        port=24800,
        remote_host="192.168.1.20",
    )


class LocateTests(unittest.TestCase):
    def test_uses_configured_core(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            core = touch(Path(tmp) / "deskflow-core")
            cfg = {"deskflow": {"path": str(core)}}
            self.assertEqual(deskflow_bridge.locate_deskflow(cfg, system="Darwin"), str(core))

    def test_uses_configured_macos_app_core(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "Deskflow.app"
            core = touch(app / "Contents" / "MacOS" / "deskflow-core")
            cfg = {"deskflow": {"path": str(app)}}
            self.assertEqual(deskflow_bridge.locate_deskflow(cfg, system="Darwin"), str(core))

    def test_falls_back_to_bundled_windows_core(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executable = touch(root / "QuickSwitch.exe")
            bundled = touch(root / "deskflow" / "deskflow-core.exe")
            with mock.patch.object(deskflow_bridge.sys, "frozen", True, create=True), \
                 mock.patch.object(deskflow_bridge.sys, "executable", str(executable)), \
                 mock.patch.object(deskflow_bridge, "VENDOR_ROOT", root / "missing"), \
                 mock.patch("deskflow_bridge._candidate_roots", return_value=()), \
                 mock.patch("deskflow_bridge.shutil.which", return_value=None):
                found = deskflow_bridge.locate_deskflow({}, system="Windows")
                self.assertEqual(Path(found).resolve(), bundled.resolve())
                self.assertTrue(deskflow_bridge.is_bundled_path(str(bundled), system="Windows"))

    def test_falls_back_to_bundled_macos_core(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executable = touch(root / "QuickSwitch.app" / "Contents" / "MacOS" / "QuickSwitch")
            bundled = touch(
                root
                / "QuickSwitch.app"
                / "Contents"
                / "Resources"
                / "deskflow"
                / "Deskflow.app"
                / "Contents"
                / "MacOS"
                / "deskflow-core"
            )
            with mock.patch.object(deskflow_bridge.sys, "frozen", True, create=True), \
                 mock.patch.object(deskflow_bridge.sys, "executable", str(executable)), \
                 mock.patch.object(deskflow_bridge, "VENDOR_ROOT", root / "missing"), \
                 mock.patch.object(deskflow_bridge, "MAC_APP_CANDIDATES", ()), \
                 mock.patch("deskflow_bridge.shutil.which", return_value=None):
                found = deskflow_bridge.locate_deskflow({}, system="Darwin")
                self.assertEqual(Path(found).resolve(), bundled.resolve())
                self.assertTrue(deskflow_bridge.is_bundled_path(str(bundled), system="Darwin"))


class RunningTests(unittest.TestCase):
    def tearDown(self) -> None:
        with deskflow_bridge._PROCESS_LOCK:
            deskflow_bridge._PROCESS = None

    def test_macos_recognizes_core_process(self) -> None:
        with mock.patch("deskflow_bridge._run_text", return_value=(0, "32512 deskflow-core\n")):
            self.assertTrue(deskflow_bridge.is_running(system="Darwin"))

    def test_windows_reads_tasklist_for_core_only(self) -> None:
        output = "deskflow-core.exe            1234 Console   1     20,000 K\r\n"
        with mock.patch("deskflow_bridge._run_text", return_value=(0, output)):
            self.assertTrue(deskflow_bridge.is_running(system="Windows"))
        with mock.patch("deskflow_bridge._run_text", return_value=(0, "deskflow.exe 1")):
            self.assertFalse(deskflow_bridge.is_running(system="Windows"))


class HotkeyTests(unittest.TestCase):
    def test_converts_keyboard_combo(self) -> None:
        self.assertEqual(deskflow_bridge._hotkey_to_deskflow("Ctrl+Alt+1"), "control+alt+1")
        self.assertEqual(deskflow_bridge._hotkey_to_deskflow("cmd+shift+space"), "super+shift+space")
        self.assertEqual(deskflow_bridge._hotkey_to_deskflow("ctrl+f12"), "control+f12")

    def test_rejects_unsupported(self) -> None:
        self.assertIsNone(deskflow_bridge._hotkey_to_deskflow("hyper+1"))
        self.assertIsNone(deskflow_bridge._hotkey_to_deskflow("ctrl+unknown"))


class ConfigTests(unittest.TestCase):
    def cfg(self, *, role: str = "client", peer_host: str = "192.168.1.20", **deskflow):
        base = {
            "role": role,
            "peer_host": peer_host,
            "hotkeys": {"switch_to_mac": "ctrl+alt+1", "switch_to_win": "ctrl+alt+2"},
            "deskflow": {"port": 24800, "mac_side": "left", **deskflow},
        }
        return base

    def test_client_settings_disable_tls_and_set_remote_host(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            text = deskflow_bridge.render_settings(self.cfg(), prepared(tmp, mode="client"))
        self.assertIn("computerName=quickswitch-client", text)
        self.assertIn("coreMode=1", text)
        self.assertIn("tlsEnabled=false", text)
        self.assertIn("remoteHost=192.168.1.20", text)
        self.assertNotIn("[server]", text)

    def test_server_settings_reference_external_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            item = prepared(tmp, mode="server")
            text = deskflow_bridge.render_settings(self.cfg(role="server"), item)
        self.assertIn("computerName=quickswitch-server", text)
        self.assertIn("coreMode=2", text)
        self.assertIn("externalConfig=true", text)
        self.assertIn(f"externalConfigFile={item.server_config_path}", text)
        self.assertIn("enableClipboard=true", text)

    def test_server_settings_escape_windows_path_for_ini_parser(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            item = replace(
                prepared(tmp, mode="server"),
                server_config_path=Path(r"D:\a\_temp\deskflow\Deskflow-server.conf"),
            )
            text = deskflow_bridge.render_settings(self.cfg(role="server"), item)
        self.assertIn(
            "externalConfigFile=D:/a/_temp/deskflow/Deskflow-server.conf",
            text,
        )

    def test_server_layout_and_hotkeys(self) -> None:
        text = deskflow_bridge.render_server_config(self.cfg())
        self.assertIn("quickswitch-server:\n        left = quickswitch-client", text)
        self.assertIn("quickswitch-client:\n        right = quickswitch-server", text)
        self.assertIn(
            "keystroke(control+alt+1) = switchToScreen(quickswitch-client)", text
        )
        self.assertIn(
            "keystroke(control+alt+2) = switchToScreen(quickswitch-server)", text
        )

    def test_mac_side_right_reverses_links(self) -> None:
        text = deskflow_bridge.render_server_config(self.cfg(mac_side="right"))
        self.assertIn("quickswitch-server:\n        right = quickswitch-client", text)
        self.assertIn("quickswitch-client:\n        left = quickswitch-server", text)

    def test_invalid_hotkeys_are_omitted(self) -> None:
        cfg = self.cfg()
        cfg["hotkeys"]["switch_to_mac"] = "hyper+1"
        text = deskflow_bridge.render_server_config(cfg)
        self.assertNotIn("switchToScreen(quickswitch-client)", text)
        self.assertIn("switchToScreen(quickswitch-server)", text)

    def test_prepare_writes_client_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            core = touch(Path(tmp) / "Deskflow.app" / "Contents" / "MacOS" / "deskflow-core")
            cfg = self.cfg(path=str(core))
            item = deskflow_bridge.prepare(cfg, system="Darwin", state_dir=Path(tmp) / "state")
            self.assertEqual(item.mode, "client")
            self.assertTrue(item.settings_path.is_file())
            self.assertIsNone(item.server_config_path)
            self.assertIn("remoteHost=192.168.1.20", item.settings_path.read_text())

    def test_prepare_writes_server_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            core = touch(Path(tmp) / "deskflow-core")
            cfg = self.cfg(role="server", path=str(core))
            item = deskflow_bridge.prepare(cfg, system="Linux", state_dir=Path(tmp) / "state")
            self.assertEqual(item.mode, "server")
            self.assertTrue(item.server_config_path.is_file())
            self.assertIn("section: links", item.server_config_path.read_text())

    def test_client_auto_without_peer_is_actionable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            core = touch(Path(tmp) / "deskflow-core")
            cfg = self.cfg(path=str(core))
            cfg["peer_host"] = "auto"
            with self.assertRaisesRegex(deskflow_bridge.DeskflowError, "自动发现"):
                deskflow_bridge.prepare(cfg, system="Linux", state_dir=Path(tmp) / "state")


class LaunchTests(unittest.TestCase):
    def tearDown(self) -> None:
        with deskflow_bridge._PROCESS_LOCK:
            deskflow_bridge._PROCESS = None

    def test_launch_uses_headless_cli_and_workdir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            item = prepared(tmp)
            process = mock.Mock(pid=4321)
            with mock.patch("deskflow_bridge.subprocess.Popen", return_value=process) as popen:
                deskflow_bridge._launch(item, system="Darwin")
            command = popen.call_args.args[0]
            self.assertEqual(command[:2], [item.core_path, "client"])
            self.assertIn("--settings", command)
            self.assertIn("--new-instance", command)
            self.assertEqual(popen.call_args.kwargs["cwd"], str(Path(item.core_path).parent))
            self.assertFalse(popen.call_args.kwargs.get("shell", False))
            self.assertEqual(item.pid_path.read_text().strip(), "4321")


class StartTests(unittest.TestCase):
    def test_missing_core_returns_actionable_error(self) -> None:
        with mock.patch("deskflow_bridge.managed_pid", return_value=None), \
             mock.patch("deskflow_bridge.is_running", return_value=False), \
             mock.patch("deskflow_bridge.locate_deskflow_core", return_value=None):
            ok, detail = deskflow_bridge.start({}, system="Linux")
        self.assertFalse(ok)
        self.assertIn("内置 Deskflow 核心", detail)

    def test_unmanaged_process_is_not_claimed(self) -> None:
        with mock.patch("deskflow_bridge.managed_pid", return_value=None), \
             mock.patch("deskflow_bridge.is_running", return_value=True):
            ok, detail = deskflow_bridge.start({}, system="Darwin")
        self.assertFalse(ok)
        self.assertIn("另一个", detail)

    def test_already_managed_returns_success(self) -> None:
        with mock.patch("deskflow_bridge.managed_pid", return_value=123), \
             mock.patch("deskflow_bridge.prepare") as prepare:
            ok, detail = deskflow_bridge.start({}, system="Darwin")
        self.assertTrue(ok)
        self.assertIn("已在运行", detail)
        prepare.assert_not_called()

    def test_start_launches_prepared_core(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            item = prepared(tmp)
            process = mock.Mock()
            process.poll.return_value = None
            with mock.patch("deskflow_bridge.managed_pid", return_value=None), \
                 mock.patch("deskflow_bridge.is_running", return_value=False), \
                 mock.patch("deskflow_bridge.prepare", return_value=item), \
                 mock.patch("deskflow_bridge._launch", return_value=process) as launch:
                ok, detail = deskflow_bridge.start({}, system="Darwin", startup_wait=0)
        self.assertTrue(ok)
        self.assertIn("client", detail)
        launch.assert_called_once_with(item, system="Darwin")

    def test_fast_exit_includes_log_tail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            item = prepared(tmp)
            item.log_path.write_text(
                "FATAL: assistive devices does not trust this process\n", encoding="utf-8"
            )
            process = mock.Mock()
            process.poll.return_value = 1
            with mock.patch("deskflow_bridge.managed_pid", return_value=None), \
                 mock.patch("deskflow_bridge.is_running", return_value=False), \
                 mock.patch("deskflow_bridge.prepare", return_value=item), \
                 mock.patch("deskflow_bridge._launch", return_value=process):
                ok, detail = deskflow_bridge.start({}, system="Darwin", startup_wait=0)
        self.assertFalse(ok)
        self.assertIn("退出码 1", detail)
        self.assertIn("assistive devices", detail)


class StopTests(unittest.TestCase):
    def tearDown(self) -> None:
        with deskflow_bridge._PROCESS_LOCK:
            deskflow_bridge._PROCESS = None

    def test_no_core_is_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("deskflow_bridge.managed_pid", return_value=None), \
                 mock.patch("deskflow_bridge.is_running", return_value=False):
                ok, detail = deskflow_bridge.stop({}, system="Darwin", state_dir=Path(tmp))
        self.assertTrue(ok)
        self.assertIn("没有", detail)

    def test_pid_is_terminated_and_file_removed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "deskflow.pid").write_text("123\n", encoding="utf-8")
            with mock.patch("deskflow_bridge.managed_pid", return_value=123), \
                 mock.patch("deskflow_bridge._pid_alive", side_effect=[True, False, False]), \
                 mock.patch("deskflow_bridge.os.kill") as kill, \
                 mock.patch("deskflow_bridge.time.sleep"):
                ok, detail = deskflow_bridge.stop({}, system="Darwin", state_dir=root)
            self.assertTrue(ok)
            self.assertIn("已停止", detail)
            kill.assert_called_once_with(123, deskflow_bridge.signal.SIGTERM)
            self.assertFalse((root / "deskflow.pid").exists())

    def test_unmanaged_core_is_not_killed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("deskflow_bridge.managed_pid", return_value=None), \
                 mock.patch("deskflow_bridge.is_running", return_value=True), \
                 mock.patch("deskflow_bridge.os.kill") as kill:
                ok, detail = deskflow_bridge.stop({}, system="Darwin", state_dir=Path(tmp))
            self.assertFalse(ok)
            self.assertIn("非 QuickSwitch", detail)
            kill.assert_not_called()


class SnapshotTests(unittest.TestCase):
    def test_reports_running_managed_headless_core(self) -> None:
        cfg = {
            "role": "client",
            "peer_host": "192.168.1.20",
            "deskflow": {"auto_start": True, "port": 24999},
        }
        with mock.patch("deskflow_bridge.locate_deskflow_core", return_value="/tmp/deskflow-core"), \
             mock.patch("deskflow_bridge.is_running", return_value=True), \
             mock.patch("deskflow_bridge.managed_pid", return_value=123), \
             mock.patch("deskflow_bridge.is_bundled_path", return_value=True), \
             mock.patch("deskflow_bridge.macos_accessibility_trusted", return_value=True), \
             mock.patch("deskflow_bridge.log_tail", return_value=""):
            status = deskflow_bridge.snapshot(cfg, system="Darwin", state_dir=Path("/tmp/qs-df"))
        self.assertEqual(status["mode"], "client")
        self.assertEqual(status["port"], 24999)
        self.assertTrue(status["running"])
        self.assertTrue(status["managed"])
        self.assertTrue(status["bundled"])
        self.assertFalse(status["tls"])
        self.assertEqual(status["peer_host"], "192.168.1.20")

    def test_permission_failure_is_surfaced(self) -> None:
        cfg = {"role": "server", "deskflow": {"auto_start": True}}
        message = "FATAL: assistive devices does not trust this process"
        with mock.patch("deskflow_bridge.locate_deskflow_core", return_value="/tmp/deskflow-core"), \
             mock.patch("deskflow_bridge.is_running", return_value=False), \
             mock.patch("deskflow_bridge.managed_pid", return_value=None), \
             mock.patch("deskflow_bridge.macos_accessibility_trusted", return_value=False), \
             mock.patch("deskflow_bridge.log_tail", return_value=message):
            status = deskflow_bridge.snapshot(cfg, system="Darwin", state_dir=Path("/tmp/qs-df"))
        self.assertTrue(status["permission_required"])
        self.assertIn("辅助功能", status["detail"])
        self.assertEqual(status["mode"], "server")


class PermissionTests(unittest.TestCase):
    def test_open_privacy_allows_only_known_pages(self) -> None:
        with mock.patch("deskflow_bridge.platform.system", return_value="Darwin"), \
             mock.patch("deskflow_bridge.subprocess.Popen") as popen:
            self.assertTrue(deskflow_bridge.open_macos_privacy_settings("accessibility"))
            self.assertIn("Privacy_Accessibility", popen.call_args.args[0][1])
            self.assertFalse(deskflow_bridge.open_macos_privacy_settings("file:///etc/passwd"))
        self.assertEqual(popen.call_count, 1)

    def test_prompt_opens_settings_only_when_untrusted(self) -> None:
        with mock.patch("deskflow_bridge.platform.system", return_value="Darwin"), \
             mock.patch("deskflow_bridge.macos_accessibility_trusted", return_value=False), \
             mock.patch("deskflow_bridge.open_macos_privacy_settings") as opener:
            self.assertFalse(deskflow_bridge.prompt_macos_accessibility())
        opener.assert_called_once_with("accessibility")


if __name__ == "__main__":
    unittest.main()
