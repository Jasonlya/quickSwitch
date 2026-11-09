"""QuickSwitch 自动启动/重启内置键鼠共享核心的行为测试。"""
from __future__ import annotations

import asyncio
import threading
import types
import unittest
import sys
from unittest import mock

from main import QuickSwitchApp


def make_app(
    auto_start: bool,
    *,
    dry_run: bool = False,
    role: str = "server",
    peer_host: str = "127.0.0.1",
) -> QuickSwitchApp:
    app = object.__new__(QuickSwitchApp)
    app.cfg = {
        "role": role,
        "peer_host": peer_host,
        "deskflow": {"auto_start": auto_start, "path": ""},
        "hotkeys": {"switch_to_mac": "ctrl+alt+1", "switch_to_win": "ctrl+alt+2"},
    }
    app.platform = "Darwin"
    app._main_thread_id = threading.get_ident()
    app.dry_run = dry_run
    app.deskflow_status = {
        "auto_start": auto_start,
        "path": "",
        "installed": True,
        "running": False,
        "system": "Darwin",
        "detail": "",
    }
    app._deskflow_checked_at = 0.0
    app._deskflow_lock = threading.RLock()
    app._deskflow_peer_host = "" if peer_host.lower() == "auto" else peer_host
    app.peer = mock.Mock()
    app.quick = mock.Mock()
    return app


def snapshot(*_args, **_kwargs):
    return {
        "auto_start": bool(_args[0].get("deskflow", {}).get("auto_start")),
        "path": "/tmp/deskflow-core",
        "installed": True,
        "running": _kwargs.pop("running", False),
        "system": "Darwin",
        "mode": "server",
        "port": 24800,
        "bundled": True,
        "managed": True,
        "tls": False,
    }


class DeskflowStartupTests(unittest.TestCase):
    def test_auto_start_launches_headless_core(self) -> None:
        app = make_app(True)
        launched = {"value": False}

        def snap(*args, **kwargs):
            result = snapshot(*args, **kwargs)
            result["running"] = launched["value"]
            return result

        def start(*_args, **_kwargs):
            launched["value"] = True
            return True, "已启动键鼠共享核心（server，端口 24800）"

        with mock.patch("main.deskflow_bridge.snapshot", side_effect=snap), \
             mock.patch("main.deskflow_bridge.start", side_effect=start) as starter, \
             mock.patch("main.time.sleep"):
            QuickSwitchApp._start_deskflow(app)

        starter.assert_called_once_with(
            app.cfg, system="Darwin", peer_host="127.0.0.1"
        )
        self.assertTrue(app.deskflow_status["running"])
        self.assertIn("已启动键鼠共享核心", app.deskflow_status["detail"])

    def test_auto_start_disabled_does_not_launch(self) -> None:
        app = make_app(False)
        with mock.patch("main.deskflow_bridge.snapshot", side_effect=snapshot), \
             mock.patch("main.deskflow_bridge.start") as starter, \
             mock.patch("main.deskflow_bridge.stop", return_value=(True, "没有正在运行的键鼠共享核心")) as stopper:
            QuickSwitchApp._start_deskflow(app)
        starter.assert_not_called()
        stopper.assert_called_once_with(app.cfg, system="Darwin")
        self.assertFalse(app.deskflow_status["running"])

    def test_disabling_auto_start_stops_managed_core(self) -> None:
        app = make_app(False)
        app.deskflow_status["running"] = True
        app.deskflow_status["managed"] = True
        with mock.patch("main.deskflow_bridge.snapshot", side_effect=snapshot), \
             mock.patch("main.deskflow_bridge.stop", return_value=(True, "已停止键鼠共享核心")) as stopper:
            QuickSwitchApp._restart_deskflow(app)
        stopper.assert_called_once_with(app.cfg, system="Darwin")
        self.assertIn("已停止内置核心", app.deskflow_status["detail"])
        self.assertFalse(app.deskflow_status["running"])
        self.assertFalse(app.deskflow_status["managed"])

    def test_dry_run_does_not_launch(self) -> None:
        app = make_app(True, dry_run=True)
        with mock.patch("main.deskflow_bridge.snapshot", side_effect=snapshot), \
             mock.patch("main.deskflow_bridge.start") as starter:
            QuickSwitchApp._start_deskflow(app)
        starter.assert_not_called()

    def test_client_auto_waits_for_discovered_windows(self) -> None:
        app = make_app(True, role="client", peer_host="auto")
        with mock.patch("main.deskflow_bridge.snapshot", side_effect=snapshot), \
             mock.patch("main.deskflow_bridge.start") as starter:
            QuickSwitchApp._start_deskflow(app)
        starter.assert_not_called()
        self.assertIn("等待自动发现", app.deskflow_status["detail"])

    def test_client_uses_concrete_peer(self) -> None:
        app = make_app(True, role="client", peer_host="192.168.1.20")
        with mock.patch("main.deskflow_bridge.snapshot", side_effect=snapshot), \
             mock.patch("main.deskflow_bridge.start", return_value=(True, "ok")) as starter, \
             mock.patch("main.time.sleep"):
            QuickSwitchApp._start_deskflow(app)
        starter.assert_called_once_with(
            app.cfg, system="Darwin", peer_host="192.168.1.20"
        )

    def test_startup_recovery_switches_back_when_cached_remote_is_offline(self) -> None:
        app = make_app(False)
        app.cfg["safety"] = {"startup_recovery": True, "startup_grace": 0}
        app._stopping = False
        app.quick.state = None
        app.quick.local_target = "win"
        app.quick.remote_target = "mac"
        app.quick.trigger = mock.AsyncMock(return_value=True)
        app.peer.connected = False
        app.read_cache = mock.Mock(return_value={"target": "mac"})

        asyncio.run(QuickSwitchApp._startup_recovery(app))

        app.quick.trigger.assert_awaited_once_with("win", source="startup-recovery")
        self.assertIn("已自动切回", app.quick.last_notice)

    def test_shutdown_sends_goodbye_before_stopping_peer(self) -> None:
        app = make_app(True)
        app._startup_recovery_task = None
        app.discovery = None
        app.quick.cancel_background_tasks.return_value = []
        app.peer.send_all = mock.AsyncMock(return_value=1)
        app.peer.stop = mock.AsyncMock()
        app.quick.name = "mac-client"

        asyncio.run(QuickSwitchApp._shutdown_async(app))

        app.peer.send_all.assert_awaited_once_with(
            {"type": "goodbye", "name": "mac-client", "reason": "shutdown"}
        )
        app.peer.stop.assert_awaited_once()

    def test_discovered_server_restarts_client_core(self) -> None:
        app = make_app(True, role="client", peer_host="auto")
        with mock.patch("main.threading.Thread") as thread_class:
            thread = thread_class.return_value
            QuickSwitchApp._on_peer_found(
                app, {"name": "win-server", "host": "192.168.1.20", "port": 8765, "role": "server"}
            )
        app.peer.set_host.assert_called_once_with("192.168.1.20", 8765)
        self.assertEqual(app._deskflow_peer_host, "192.168.1.20")
        thread_class.assert_called_once()
        thread.start.assert_called_once()
        self.assertEqual(thread_class.call_args.kwargs["kwargs"]["reason"], "已发现 Windows")

    def test_discovery_ignores_client_peer_on_server(self) -> None:
        app = make_app(True, role="server", peer_host="auto")
        with mock.patch("main.threading.Thread") as thread_class:
            QuickSwitchApp._on_peer_found(
                app, {"name": "mac-client", "host": "192.168.1.30", "port": 8765, "role": "client"}
            )
        thread_class.assert_not_called()

    def test_apply_live_config_restarts_only_for_local_fields(self) -> None:
        app = make_app(True)
        with mock.patch.object(QuickSwitchApp, "_restart_deskflow") as restart:
            self.assertTrue(app.apply_live_config(["deskflow.port"]))
        restart.assert_called_once_with("配置已更新")
        self.assertFalse(app.apply_live_config(["peer_host"]))

    def test_apply_live_hotkeys_reregisters_and_restarts(self) -> None:
        app = make_app(True)
        app._setup_hotkeys = mock.Mock()
        with mock.patch.object(QuickSwitchApp, "_restart_deskflow") as restart:
            self.assertTrue(app.apply_live_config(["hotkeys.switch_to_mac"]))
        app._setup_hotkeys.assert_called_once()
        restart.assert_called_once()

    def test_hotkey_reregistration_unhooks_old_combinations(self) -> None:
        app = object.__new__(QuickSwitchApp)
        app.cfg = {
            "role": "server",
            "hotkeys": {"switch_to_mac": "Ctrl+Alt+1", "switch_to_win": "ctrl+alt+2"},
        }
        app._keyboard = None
        app.hotkeys_registered = False
        app.hotkeys_reason = ""
        fake = mock.Mock()
        with mock.patch.dict(sys.modules, {"keyboard": fake}):
            QuickSwitchApp._setup_hotkeys(app)
            app.cfg["hotkeys"]["switch_to_mac"] = "ctrl+shift+f8"
            QuickSwitchApp._setup_hotkeys(app)
        self.assertEqual(fake.unhook_all_hotkeys.call_count, 2)
        registered = [call.args[0] for call in fake.add_hotkey.call_args_list]
        self.assertEqual(registered, ["ctrl+alt+1", "ctrl+alt+2", "ctrl+shift+f8", "ctrl+alt+2"])
        self.assertTrue(app.hotkeys_registered)

    def test_macos_client_registers_local_hotkeys(self) -> None:
        app = make_app(True, role="client")
        app._mac_hotkeys = None
        app.hotkeys_registered = False
        app.hotkeys_reason = ""
        manager = mock.Mock()
        with mock.patch("main.mac_hotkeys.MacHotkeyManager", return_value=manager):
            QuickSwitchApp._setup_hotkeys(app)
        self.assertEqual(manager.register.call_count, 2)
        self.assertTrue(app.hotkeys_registered)
        self.assertIn("本机已注册", app.hotkeys_reason)
        self.assertIs(app._mac_hotkeys, manager)

    def test_macos_client_records_missing_hotkeys(self) -> None:
        app = make_app(True, role="client")
        app.cfg["hotkeys"] = {"switch_to_mac": "", "switch_to_win": ""}
        app._mac_hotkeys = None
        manager = mock.Mock()
        with mock.patch("main.mac_hotkeys.MacHotkeyManager", return_value=manager):
            QuickSwitchApp._setup_hotkeys(app)
        self.assertFalse(app.hotkeys_registered)
        self.assertIn("为空", app.hotkeys_reason)
        manager.close.assert_called_once()

    def test_macos_hotkey_update_from_worker_is_deferred_to_main_thread(self) -> None:
        app = make_app(True, role="client")
        app._main_thread_id = -1
        helper = types.SimpleNamespace(callAfter=mock.Mock())
        package = types.ModuleType("PyObjCTools")
        package.AppHelper = helper
        with mock.patch.dict(
            sys.modules,
            {"PyObjCTools": package, "PyObjCTools.AppHelper": helper},
        ):
            QuickSwitchApp._setup_hotkeys(app)
        helper.callAfter.assert_called_once_with(app._setup_hotkeys)
        self.assertIn("正在应用", app.hotkeys_reason)

    def test_clipboard_normalizer_starts_and_stops(self) -> None:
        app = make_app(True, role="client")
        app._mac_clipboard = None
        fake = mock.Mock()
        fake.running = False
        fake.start.return_value = True
        with mock.patch("main.mac_clipboard.MacClipboardNormalizer", return_value=fake) as factory:
            QuickSwitchApp._setup_clipboard_normalizer(app)
        factory.assert_called_once()
        fake.start.assert_called_once()

        app.cfg["deskflow"]["clipboard_enabled"] = False
        QuickSwitchApp._setup_clipboard_normalizer(app)
        fake.stop.assert_called_once()
        self.assertIsNone(app._mac_clipboard)

    def test_refresh_keeps_last_failure_detail(self) -> None:
        app = make_app(True)
        app.deskflow_status["detail"] = "上次失败：需要辅助功能权限"
        with mock.patch("main.deskflow_bridge.snapshot", side_effect=snapshot):
            status = QuickSwitchApp._refresh_deskflow_status(app)
        self.assertEqual(status["detail"], "上次失败：需要辅助功能权限")

    def test_macos_permission_settings_open_only_once(self) -> None:
        app = make_app(True)
        app._permission_prompted = False
        with mock.patch("main.deskflow_bridge.prompt_macos_accessibility", return_value=False) as prompt:
            QuickSwitchApp._prompt_macos_permission_once(app)
            QuickSwitchApp._prompt_macos_permission_once(app)
        prompt.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
