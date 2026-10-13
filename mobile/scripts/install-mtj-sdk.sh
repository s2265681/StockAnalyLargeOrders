#!/usr/bin/env bash
# 从百度统计后台下载的 SDK 压缩包安装到 mobile/src/utils/
# 用法: ./scripts/install-mtj-sdk.sh ~/Downloads/微信小程序统计SDK.zip
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/src/utils"
ZIP="${1:?请传入 SDK zip 路径，在百度统计接入页点击「下载微信小程序统计SDK」}"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
unzip -q -o "$ZIP" -d "$TMP"

JS=$(find "$TMP" -name 'mtj-wx-sdk.js' | head -1)
if [[ -z "$JS" ]]; then
  echo "zip 里未找到 mtj-wx-sdk.js" >&2
  exit 1
fi

cp "$JS" "$DEST/mtj-wx-sdk.js"
echo "已安装: $DEST/mtj-wx-sdk.js"
echo "config 已配置 AppKey: 6c5f1aedf6 → $DEST/mtj-wx-sdk.config.js"
