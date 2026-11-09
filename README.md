# QuickSwitch

[![Release: latest](docs/images/badge-release.svg)](https://github.com/Jasonlya/quickswitch/releases/latest)
[![License: MIT](docs/images/badge-license.svg)](LICENSE)

一键切换**显示器输入源**和**键鼠控制权**，并在两台电脑之间双向共享**剪贴板**（文本、HTML、图片）。Windows 与 Mac 共用一台显示器，按 `Ctrl+Alt+1` 切到 Mac，按 `Ctrl+Alt+2` 切回 Windows；组合键可以自行录制。macOS 复制图片时会额外写入 Windows 可解码的 BMP，避免粘贴成文件名。

> ⭐ **如果 QuickSwitch 帮到了你，欢迎点个 [Star](https://github.com/Jasonlya/quickswitch)。** 这是对项目最直接的支持，也能帮助更多需要双机切换的人发现它。

![QuickSwitch 主界面：两个切换按钮、按钮内的热键标记和折叠的信息入口](docs/images/quickstart.png)

## 下载安装

**不需要 Python、pip，也不需要手动安装运行库。** 到 [Releases](https://github.com/Jasonlya/quickswitch/releases/latest) 下载对应安装包：

| 你的电脑 | 下载文件 | 安装方法 |
| --- | --- | --- |
| Mac（Apple 芯片 M1/M2/M3/M4） | `QuickSwitch-*-macOS-arm64.dmg` | 打开 DMG，把 QuickSwitch 拖进「应用程序」 |
| Windows 10/11 64 位 | `QuickSwitch-Setup-*.exe` | 双击安装，按提示下一步即可 |

macOS 版只支持 Apple Silicon，不提供 Intel Mac 安装包。安装包已经自带 Python 运行时、托盘依赖和原生设置窗口，目标电脑不需要开发环境。

**键鼠共享核心也已内置。** QuickSwitch 会以无界面方式自动启动随包的 Deskflow 核心；Windows 和 macOS 都不需要安装、配置或打开 Deskflow 客户端。

**睡眠 / 关机保护。** 切换前会先确认目标电脑仍在响应；目标已睡眠、关机或 QuickSwitch 未运行时，保留当前显示器输入并提示原因，不会把屏幕切到无信号输入。对端异常失联后的自动回切默认关闭，可在设置里按需开启；正常退出 QuickSwitch 会发送 goodbye，不会触发回切。也可启用 Wake-on-LAN 尝试唤醒目标机（受网卡、BIOS、Apple Silicon 睡眠方式和路由器广播设置限制）。

> **当前安装包未签名。** macOS 首次打开若提示「无法验证开发者」，请右键 QuickSwitch →「打开」→ 再点「打开」；Windows 首次运行若出现 SmartScreen，请点「更多信息」→「仍要运行」。

## 使用前准备

QuickSwitch 负责切换显示器输入源，并直接管理内置的键鼠共享核心：

| 需要准备 | 作用 | 在哪里获取 |
| --- | --- | --- |
| 键鼠共享核心（已内置） | 让一套键鼠控制两台电脑 | 无需单独下载或打开客户端；安装包包含 Deskflow 1.27.0 无界面核心 |
| 显示器 DDC/CI | 允许电脑切换显示器的输入源 | 按显示器机身按钮打开 OSD 菜单，在「系统 / 设置 / 其他设置」里找 DDC/CI；多数型号默认开启，详细路径见 [INSTALL.md](INSTALL.md#11-开启显示器-ddcci) |

键鼠接在 Windows 上时，QuickSwitch 会自动让 Windows 作为服务端、Mac 作为客户端；屏幕左右位置、连接地址、端口和切换热键都由 QuickSwitch 生成并同步给它管理的核心。两台电脑也会各自注册本机切换热键，因此在 Mac 键盘上按同一个组合键同样可以切换显示器。

Windows 端已内置原生 DDC（DXVA2），**不需要安装 ControlMyMonitor**。macOS 端需要 Apple Silicon，并安装 [m1ddc](https://github.com/waydabber/m1ddc)；如果 Mac 端提示找不到 DDC 工具，按安装文档确认 `ddc.m1ddc_path`。

## 首次配置

1. 两台电脑都安装并启动 QuickSwitch。首次启动会自动弹出**配置向导**。
2. **连接**：推荐选「自动发现」；需要手动填 IP 时，把另一台电脑向导左侧显示的「本机 IP」填进来。
3. **安全**：点「生成」得到 6 位配对码，复制或手动输入到另一台电脑。两端配对码必须完全一致。
4. **显示器**：点「读取」确认当前输入源，再标记为 Mac 或 Windows；也可以直接填写已知数值，或点「探测」让程序试探。
5. **完成**：检查摘要后点「完成配置」。关闭设置窗口，从菜单栏/托盘菜单退出 QuickSwitch，再重新打开，让连接配置生效。

向导只在首次配置时自动出现。以后要修改，展开「更多信息与设置」→「配置」，点「重新运行配置向导」。

macOS 首次使用键鼠共享时，需要在「系统设置 → 隐私与安全性」中允许 QuickSwitch（权限列表里也可能显示 Deskflow 或 deskflow-core）使用**辅助功能**、**输入监控**和**本地网络**。如果核心因为缺少权限退出，QuickSwitch 会自动打开一次辅助功能设置页；键鼠共享状态也会显示「需要权限」。授权后展开「更多信息与设置 → 键鼠共享」，点「重启键鼠共享」即可。设置页还提供「打开辅助功能设置」和「打开输入监控设置」两个按钮。

> `v2.0.4` 及更早版本升级后，如果开关已经打开仍提示「需要权限」，这是 Ad-hoc 签名绑定的旧 cdhash 失效。升级到 `v2.0.5` 后点设置页「重建 macOS 授权」，再重新打开两个开关即可；后续版本不会重复出现。

## 技术文档与开发

- [安装、日常使用与排错](INSTALL.md)
- [完整技术文档](docs/TECHNICAL.md)：配置项、通信协议、接口、验收与打包细节
- [从源码运行](docs/TECHNICAL.md)：需要 Python 3.9+，普通用户不需要这一步

发布新版本时，维护者推送 `v*` 标签即可触发 GitHub Actions，自动构建 macOS DMG 和 Windows 安装包：

```bash
git tag v2.2.3
git push origin v2.2.3
```

构建产物会出现在仓库的 **Releases** 页面。

## 架构

[![QuickSwitch 运行架构](docs/images/quickswitch-architecture.gif)](https://jasonlya.github.io/quickswitch/architecture/)

点击动图打开可交互版本，可切换深色/浅色主题，并查看主链路、键鼠共享和控制状态。

## 开源鸣谢

QuickSwitch 的实现离不开这些开源项目及其维护者、贡献者：

- [Deskflow](https://github.com/deskflow/deskflow)：键鼠共享、剪贴板共享和跨设备控制核心。安装包内置未经修改的 Deskflow 1.27.0 无界面构建，遵循 GPL-2.0（附 OpenSSL 例外）。
- [m1ddc](https://github.com/waydabber/m1ddc)：Apple Silicon Mac 上的 DDC/CI 显示器输入源读取与切换，遵循 MIT。
- [pywebview](https://github.com/r0x0r/pywebview)、[Pillow](https://github.com/python-pillow/Pillow)、[pystray](https://github.com/moses-palmer/pystray)、[keyboard](https://github.com/boppreh/keyboard)：分别用于设置窗口、图像与托盘图标、系统托盘和 Windows 全局热键；macOS 热键由系统 Carbon API 注册。
- [PyInstaller](https://github.com/pyinstaller/pyinstaller)：构建 macOS App 与 Windows 安装包。

感谢上述项目作者与所有贡献者。完整许可证说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。QuickSwitch 与这些项目不存在隶属关系，也不代表其官方认可。

## 免责声明

- QuickSwitch 是个人开源项目，与 Deskflow、Apple、Microsoft、显示器厂商及上述第三方项目均无隶属、合作或官方背书关系。
- 本软件按 [MIT License](LICENSE) 的「现状」提供，不附带任何明示或默示担保。作者不对因使用或无法使用本软件造成的直接或间接损失承担责任。
- DDC/CI 的行为取决于显示器、线缆、转接设备、驱动和系统实现，可能出现切换失败、黑屏、分辨率异常或显示器状态异常。请先确认可通过显示器按钮恢复输入源；在远程、无人值守或关键工作环境中请谨慎使用。
- 键鼠共享与剪贴板同步会传输键盘、鼠标和剪贴板内容。请仅在可信的本地网络中使用，妥善保管配对码，并遵守所在组织的数据与设备使用政策。配置不当可能造成数据泄露或误操作。
- 请勿将本项目用于医疗、工业控制、交通运输、生产系统或其他一旦故障可能造成人身伤害、重大财产损失的高风险场景。第三方组件由其各自作者维护，适用各自的许可证与免责声明。

## License

[MIT](LICENSE) © 2026 Jasonlya
