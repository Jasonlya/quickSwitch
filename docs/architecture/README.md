# QuickSwitch 架构图

- `quickswitch.html`：Archify 生成的独立交互版，可切换深色/浅色主题和动效。
- `../images/quickswitch-architecture.gif`：README 内联动图。
- `../images/quickswitch-architecture.png`：静态预览。

静态站点入口为 `docs/architecture/index.html`。推送到 `main` 后，`.github/workflows/pages.yml` 会自动发布 `docs/`；首次运行会尝试自动启用 GitHub Pages。

`https://jasonlya.github.io/quickswitch/architecture/`

本地预览：

```bash
python3 -m http.server 8000 --directory docs
# http://127.0.0.1:8000/architecture/
```
