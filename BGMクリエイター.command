#!/bin/bash
set -e

cd "$(dirname "$0")"

pause_on_error() {
    status=$?
    if [ "$status" -ne 0 ] && [ -t 0 ]; then
        echo
        read -r -p "起動できませんでした。Enterキーで閉じます。" _
    fi
}
trap pause_on_error EXIT

fail() {
    echo "エラー: $1" >&2
    exit 1
}

if command -v python3.13 >/dev/null 2>&1; then
    bootstrap_python="$(command -v python3.13)"
elif command -v python3 >/dev/null 2>&1; then
    bootstrap_python="$(command -v python3)"
else
    fail "Python 3.13が見つかりません。python.orgからインストールしてください。"
fi

"$bootstrap_python" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 13) else 1)' \
    || fail "Python 3.13以降が必要です。現在: $("$bootstrap_python" --version 2>&1)"
"$bootstrap_python" -c 'import tkinter' \
    || fail "Tkinterが見つかりません。python.org版のPython 3.13をインストールしてください。"

python_path=".venv/bin/python"
if [ -d .venv ] && [ ! -x "$python_path" ]; then
    fail ".venvがmacOS用ではありません。.venvを別の場所へ移してから、もう一度起動してください。"
fi

if [ ! -x "$python_path" ]; then
    echo "初回セットアップ: 仮想環境を作成しています…"
    "$bootstrap_python" -m venv .venv
    "$python_path" -m pip install -r requirements.txt
fi

if ! "$python_path" -c "import importlib.util,sys; sys.exit(0 if all(importlib.util.find_spec(m) for m in ['numpy','scipy','pygame','sounddevice']) else 1)"; then
    echo "必要なライブラリを準備しています…"
    "$python_path" -m pip install -r requirements.txt
fi

if ! "$python_path" -c "import json,pathlib,sys; p=pathlib.Path('assets/samples/manifest.json'); sys.exit(0 if p.exists() and all((p.parent/s['file']).exists() for s in json.loads(p.read_text(encoding='utf-8'))['samples']) else 1)"; then
    echo "音源をダウンロードしています…"
    "$python_path" fetch_samples.py
fi

"$python_path" app.py
