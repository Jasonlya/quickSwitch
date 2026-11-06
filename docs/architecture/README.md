# QuickSwitch 架构图

- `quickswitch.html`：Archify 生成的独立交互版，可切换深色/浅色主题和动效。
- `../images/quickswitch-architecture.gif`：README 内联动图。
- `../images/quickswitch-architecture.png`：静态预览。

静态站点入口为 `docs/architecture/index.html`。在 GitHub 仓库设置中将 Pages 的来源设为 `main` 分支的 `/docs` 目录后，访问：

`https://jasonlya.github.io/quickswitch/architecture/`

本地预览：

```bash
python3 -m http.server 8000 --directory docs
# http://127.0.0.1:8000/architecture/
```
