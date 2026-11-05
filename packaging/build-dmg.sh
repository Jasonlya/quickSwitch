#!/usr/bin/env bash
# QuickSwitch macOS 安装包：把 .app 打成 DMG（拖进 Applications 即安装）
#
# 用法：
#   packaging/build-dmg.sh                     # 用 dist/QuickSwitch.app，输出 dist/QuickSwitch-<版本>-macOS-<arch>.dmg
#   packaging/build-dmg.sh --app 路径.app --out /tmp/QuickSwitch.dmg
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
APP="${PROJECT_DIR}/dist/QuickSwitch.app"
VERSION="$("${PYTHON:-python3}" "${SCRIPT_DIR}/print-version.py")"
HOST_ARCH="$(uname -m)"
case "$HOST_ARCH" in
    arm64) ARCH="arm64" ;;
    x86_64) ARCH="x64" ;;
    *) ARCH="$HOST_ARCH" ;;
esac
OUT="${PROJECT_DIR}/dist/QuickSwitch-${VERSION}-macOS-${ARCH}.dmg"
VOLNAME="QuickSwitch"

die() { printf '错误：%s\n' "$*" >&2; exit 1; }
info() { printf '  %s\n' "$*"; }

while [ $# -gt 0 ]; do
    case "$1" in
        --app) shift; APP="${1:-}" ;;
        --out) shift; OUT="${1:-}" ;;
        --volname) shift; VOLNAME="${1:-}" ;;
        -h|--help) sed -n '2,7p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) die "未知参数：$1" ;;
    esac
    shift
done

[ -d "$APP" ] || die "找不到 ${APP}，请先运行 packaging/build-macos.sh"
[ -x "${APP}/Contents/MacOS/QuickSwitch" ] || die "${APP} 不是有效的 QuickSwitch.app"
mkdir -p "$(dirname "$OUT")"

STAGE="$(mktemp -d /tmp/quickswitch-dmg.XXXXXX)"
MNT="$(mktemp -d /tmp/quickswitch-mnt.XXXXXX)"
cleanup() {
    hdiutil detach "$MNT" -quiet >/dev/null 2>&1 || true
    rm -rf "$STAGE" "$MNT"
}
trap cleanup EXIT

info "准备安装包内容"
ditto "$APP" "$STAGE/QuickSwitch.app"
ln -s /Applications "$STAGE/Applications"
cat > "$STAGE/安装说明.txt" <<'TXT'
QuickSwitch 安装说明

1. 把左边的 QuickSwitch.app 拖到右边的 Applications（应用程序）文件夹。
2. 打开「启动台」或「应用程序」，双击 QuickSwitch。
3. 首次打开若提示「无法验证开发者」：
   在 QuickSwitch 上右键 →「打开」→ 再点「打开」。
   （这是未签名版本的系统提示；签名并公证的版本不会出现。）
4. 启动后菜单栏会出现图标，首次运行会自动打开设置页面：
   填「对端地址」（另一台电脑的局域网 IP）、选好角色、两端填同一个预共享密钥，
   保存后即可使用。

详细步骤见项目里的 INSTALL.md。
TXT

info "生成 DMG：$(basename "$OUT")"
hdiutil create -volname "$VOLNAME" -srcfolder "$STAGE" -fs HFS+ -format UDZO \
    -imagekey zlib-level=9 -ov "$OUT" >/dev/null

info "校验挂载"
hdiutil attach "$OUT" -nobrowse -readonly -mountpoint "$MNT" >/dev/null
[ -d "${MNT}/QuickSwitch.app" ] || die "DMG 里没有 QuickSwitch.app"
[ -L "${MNT}/Applications" ] || die "DMG 里缺少 Applications 快捷方式"
hdiutil detach "$MNT" -quiet >/dev/null

printf '\n完成\n'
info "产物：${OUT}"
info "大小：$(du -h "$OUT" | cut -f1)"
info "SHA256：$(shasum -a 256 "$OUT" | cut -d' ' -f1)"
