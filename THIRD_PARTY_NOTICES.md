# Third-Party Notices

QuickSwitch itself is licensed under the MIT License (see `LICENSE`).

This file records the third-party open-source projects used by QuickSwitch. The
upstream projects retain their respective copyrights and licenses; nothing in
this notice transfers ownership or grants rights beyond those licenses.

## Deskflow 1.27.0

QuickSwitch redistributes an unmodified official Deskflow build so that users do not need to download Deskflow separately.

- Project: <https://deskflow.org/>
- Source code: <https://github.com/deskflow/deskflow/tree/v1.27.0>
- Release: <https://github.com/deskflow/deskflow/releases/tag/v1.27.0>
- License: GNU General Public License version 2.0 (GPL-2.0), with the upstream OpenSSL exception
- Windows asset: `deskflow-1.27.0-win-x64-portable.zip`
  - SHA256: `8d19004cc3625623489d96580c1b58fd13ee78185689907fd4478595f93fab9a`
- macOS asset: `deskflow-1.27.0-macos-arm64.dmg`
  - SHA256: `dd21e79e566314394214906d3338c505d337af536fc580c022ee3fadffad0c97`

The upstream `LICENSE` and `LICENSE_EXCEPTION` files are included with the bundled Windows files and inside the bundled macOS `Deskflow.app`. The QuickSwitch GitHub release also publishes the corresponding Deskflow source archive so recipients can obtain the complete corresponding source.

Deskflow remains a separate upstream program. QuickSwitch generates runtime configuration, launches only the bundled headless `deskflow-core`, reports its status, and stops the process it started. It does not modify the upstream Deskflow source or open the Deskflow GUI.

## Runtime Dependencies

QuickSwitch uses the following Python packages at runtime. They are installed
from their official distributions and remain subject to their upstream licenses.

| Package | Purpose | License | Upstream |
| --- | --- | --- | --- |
| pystray 0.19.5 | System tray integration | LGPL-3.0 | <https://github.com/moses-palmer/pystray> |
| Pillow 10.4.0 | Image processing and tray/app icons | HPND | <https://github.com/python-pillow/Pillow> |
| pywebview 6.2.1 | Native settings window (WKWebView / WebView2) | BSD-3-Clause | <https://github.com/r0x0r/pywebview> |
| keyboard 0.13.5 | Global hotkeys on Windows | MIT | <https://github.com/boppreh/keyboard> |

The canonical license text for each package is available from the upstream
project and the metadata included in its published distribution.

## Build-Time Dependency

PyInstaller is used to build the macOS application and Windows executable. It is
a build tool and is not part of QuickSwitch's application logic.

- Project: <https://github.com/pyinstaller/pyinstaller>
- License: GPL-2.0-or-later with PyInstaller's special exception permitting use
  of the bootloader to build and distribute programs under other terms

## Optional External Tools

These tools are not bundled with QuickSwitch and are not required on both
platforms. If installed separately by the user, they remain subject to their own
licenses and terms.

- **m1ddc** (macOS, required for DDC/CI input switching): MIT License,
  <https://github.com/waydabber/m1ddc>
- **ddcutil** (optional Linux integration): GPL-2.0,
  <https://www.ddcutil.com/>
- **ControlMyMonitor** (optional Windows DDC fallback): a freeware utility by
  NirSoft, <https://www.nirsoft.net/utils/control_my_monitor.html>
- **BetterDisplay** (optional custom DDC read/write integration): a separately
  licensed macOS application, <https://github.com/waydabber/BetterDisplay>

## Disclaimer

QuickSwitch is an independent project and is not affiliated with or endorsed by
Deskflow, Apple, Microsoft, display manufacturers, or any third-party project
listed above. Third-party software is provided by its respective authors under
its own terms and without warranty from the QuickSwitch maintainers. See the
project README for the full usage disclaimer.
