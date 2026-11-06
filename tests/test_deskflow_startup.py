"""QuickSwitch 自动启动/重启内置键鼠共享核心的行为测试。"""
from __future__ import annotations

import threading
import unittest
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

    def test_refresh_keeps_last_failure_detail(self) -> None:
        app = make_app(True)
        app.deskflow_status["detail"] = "上次失败：需要辅助功能权限"
        with mock.patch("main.deskflow_bridge.snapshot", side_effect=snapshot):
            status = QuickSwitchApp._refresh_deskflow_status(app)
        self.assertEqual(status["detail"], "上次失败：需要辅助功能权限")


if __name__ == "__main__":
    unittest.main()
