# Third-Party Notices

QuickSwitch itself is licensed under the MIT License (see `LICENSE`).

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
