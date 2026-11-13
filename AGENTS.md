# BGMクリエイター

このプロジェクトはWindows向けの自作ループBGM制作ツール。会話で曲を依頼されたら、`bgm.py` と既存の `song.json` を使い、`outputs/` 以下の新しいフォルダへ出力する。既存の曲を上書きしない。

- Python: `.venv/Scripts/python.exe`。UI: `app.py`。起動: `BGMクリエイター.cmd`。
- `README.md` に操作手順・CLI・JSON仕様・制限を記載。
- 曲全体を変えずに一つのパートだけ修正する依頼では、他パートの音符・楽器・パラメータを維持する。
- 実音源は `assets/samples/manifest.json` に出典とSHA-256を記録。追加音源は利用条件を確認し、出典を残す。
- 音源の利用条件と、生成曲の独自性・権利に関する保証を混同しない。
- 鼻歌解析は `humming.py`、録音・取り込み画面は `humming_ui.py`。元音声は外部送信しない。マイクはユーザーの録音操作でのみ開始する。
- 鼻歌由来のメロディを自動生成に置き換えたら、そのパートの `source` を削除して出典を正しく保つ。
- コアを変更した場合は `.venv/Scripts/python.exe -m unittest -v test_bgm test_humming test_app_humming` を実行。
- UIはTkinterデスクトップアプリ。外部APIやサービスへの送信は行わない。
