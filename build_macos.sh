#!/usr/bin/env bash
# Build the macOS .app bundle. Run on macOS only: PyInstaller cannot cross-compile.
set -euo pipefail

cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
# 允许用标签名直接传入（v1.1.0），Info.plist 里只保留数字部分
APP_VERSION="${PROPHET_VERSION:-1.1.0}"
APP_VERSION="${APP_VERSION#v}"
export PROPHET_VERSION="$APP_VERSION"

# Finder 图标来自 assets 里的 PNG，用系统工具合成 .icns
ICON_PNG="assets/prophet_icon_light.png"
ICONSET="build/icon.iconset"
ICNS="build/prophet.icns"
mkdir -p "$ICONSET"
for size in 16 32 128 256 512; do
    sips -z "$size" "$size" "$ICON_PNG" --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
    double=$((size * 2))
    sips -z "$double" "$double" "$ICON_PNG" --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$ICNS"
export PROPHET_ICON="$PWD/$ICNS"

"$PYTHON" -m PyInstaller --noconfirm --clean --distpath "$PWD/dist-native" Prophet.spec

BUNDLE="dist-native/Prophet.app"
BINARY="$BUNDLE/Contents/MacOS/Prophet"

# .app 是窗口程序：重定向才能拿到自检输出，失败时按成功标记判定
mkdir -p build
"$BINARY" --self-test >build/self-test.out.log 2>build/self-test.err.log || true
if ! grep -qs "native desktop self-check passed" build/self-test.out.log build/self-test.err.log; then
    echo "--- self-test stdout ---"
    cat build/self-test.out.log || true
    echo "--- self-test stderr ---"
    cat build/self-test.err.log || true
    echo "Packaged self-test did not report success: $BINARY --self-test" >&2
    exit 1
fi

echo "Bundle ready: $PWD/$BUNDLE"
