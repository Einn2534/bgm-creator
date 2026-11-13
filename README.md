# Loop Atelier — BGMクリエイター

Windows / macOS用のローカルBGM制作ツールです。テンポ、調、音符、楽器をJSONの「設計図」に保存し、同じ設計図と音源から同じ音声を生成します。外部の音楽生成APIやAPIキーは使いません。

## 起動

### Windows

**`BGMクリエイター.cmd` をダブルクリック**してください。

### macOS

1. [python.org](https://www.python.org/downloads/macos/) からPython 3.13以降をインストールします。Apple Silicon / Intel Macのどちらでも利用できます。
2. 初回だけターミナルでこのフォルダへ移動し、次を実行します。

```bash
chmod +x "BGMクリエイター.command"
./BGMクリエイター.command
```

次回からはFinderで **`BGMクリエイター.command` をダブルクリック**して起動できます。macOSに開くことを止められた場合は、ファイルをControlキーを押しながらクリックして「開く」を選んでください。

どちらのOSでも、このフォルダ内にPython仮想環境を作り、必要なライブラリと音源を準備します。初回の準備にはインターネットが必要です。準備後の作曲・再生・WAV出力はオフラインで動作します。MP3出力とWAV以外の鼻歌読み込みには、PATH上のffmpegが必要です。macOSではHomebrewを利用している場合 `brew install ffmpeg` で追加できます。

1. 「▶ ループ再生」で最初の曲を試聴。
2. 雰囲気、小節数、シードを選び「新しい曲を作る」。シードを変えると別のフレーズになります。
3. 同じ曲の速さ・キー・長調/短調・楽器を変えるときは「設定を反映」。音符の度数は保たれます。
4. 音量・消音・残響を調整し、再生し直して比較。「この音だけ」で単独試聴できます。単独試聴は消音設定に関係なくそのパートを鳴らします。
5. 各パートの「作り直す」で、そのパートの音符のみ再生成。他のパートの音符とミックス前の音声は保持します。
6. 「ひとつ前に戻す」で変更前後を比較。「設計図を保存」で再編集用JSONを保存。
7. 「音声を書き出す」で保存先を選ぶと、日時つきの新しいフォルダへ保存します。

小節数・シードの変更は新曲作成に使用します。「新しい曲を作る」はプリセットの楽器・音量に戻ります。「ひとつ前に戻す」は曲生成・設定反映・パート再生成を対象とし、音量スライダー単独の履歴は保存しません。再生中に設定を変えた場合は、再生し直すと反映されます。

## 鼻歌からメロディを取り込む

1. 伴奏の雰囲気・テンポ・調・小節数を決めて曲を作ります。
2. **「鼻歌を取り込む…」** を押します。
3. 録音済みのWAV・MP3・M4Aなどを選ぶか、**「● マイク録音」→歌う→「■ 録音停止」** で録音します。パソコンの既定の入力マイクを使います。
4. フレーズの長さ、リズム補正、音程補正を選んで **「メロディとして取り込む」** を押します。
5. 「この音だけ」でメロディを確認し、全体のループ再生で伴奏と試聴。楽器の変更や通常の書き出しができます。「ひとつ前に戻す」で元のメロディに戻せます。

- **長さ**：自動、または1/2/4/8/16/32小節（曲の小節数以下）。前後の無音を除き、近い長さに伸縮して曲全体に繰り返します。自動は録音の長さと現在のBPMから近い小節数を選びます。テンポ自体の自動推定は行いません。
- **リズム**：16分音符・8分音符へ拍位置と長さをそろえるか、「原リズム」で音符と休符の長さの比率を保ちます。フレーズ全体の長さは、いずれも選んだ小節数に合わせます。
- **音程**：「鼻歌の音程を保持」は検出した音を半音単位に丸め、調に含まれない音も臨時記号として保持します。「曲の調に合わせる」は現在の長調・短調の近い音に補正します。伴奏のコード進行は変更しません。
- **録音**：マイクは録音ボタンを押したときだけ使用し、最大60秒で自動停止します。録音は `outputs/recordings/` に保存します。外部ファイルは120秒以内。WAV以外はffmpegで読み込みます。
- **macOSのマイク許可**：初回録音時に表示される許可画面でマイク利用を許可してください。拒否した場合は「システム設定」→「プライバシーとセキュリティ」→「マイク」で、起動に使ったターミナルの許可を変更できます。
- **保存**：抽出した音符と元音声のファイル名・SHA-256・補正設定を設計図に保存します。元音声がなくても設計図から再生できます。BGMに入るのは選んだ楽器の音です。音声のアップロードや外部AIへの送信は行いません。

静かな場所で、伴奏なしの鼻歌を一音ずつ少し長めに録ってください。和音・複数の声・大きな雑音・速い装飾音は誤検出しやすく、音符の完全な再現は保証できません。音が検出できない場合は既存の曲を変更せずエラーを表示します。

## 出力

| ファイル | 内容 |
| --- | --- |
| `loop.wav` | 44.1kHz / ステレオ / 16bit、整数小節のループ |
| `loop.mp3` | MP3も保存を選んだ場合。再生ソフトによって継ぎ目に隙間が出るため、ループ用途にはWAVを推奨 |
| `loop_check.wav` | 同じ音声を3周連結。プレーヤーの再開待ちなしで継ぎ目を確認 |
| `rhythm.wav` ほか | 音量・定位・残響を反映した5パートの個別音声。消音中も出力 |
| `transition.wav` | 最後の1小節と短い余韻から作ったフェードアウトつきの場面転換音 |
| `song.json` | 再編集できる曲の設計図 |
| `sources.json` | 使用音源・URL・ライセンス・チェックサム・合成楽器の記録 |

ループ音声はフェードアウトさせず、音符の余韻と残響を次の周回へ回し込みます。合計音量が大きい場合はミックス全体を下げてクリッピングを防ぎます。パート別ファイルにも個別に安全な音量調整が入るため、それらを外部で単純合算すると全体ミックスと完全一致しない場合があります。

## 用意した音

- 実音源：木琴、マリンバ、グロッケン、弦ピチカート。VSCO 2 Community Editionの少数の音を移調して使用します。
- 内蔵合成：プラックベース、柔らかい鍵盤、フルート風、矩形波、三角波、パーカッション。
- プリセット：明るい散歩道、静かな作業部屋、少し切ない夕暮れ、レトロゲーム。

音の数と編曲の型を絞った初版です。レトロゲームはゲーム機風の音色・アルペジオであり、実機の正確なエミュレーションではありません。録音した合いの手、ピアノロール、自然言語で作曲するアプリ内AIは未実装です。Codexへの会話で設計図やプログラムを編集できます。

## 音源を追加する

### 既存楽器の音域を増やす

木琴やマリンバなど、すでにある楽器へWAVを追加する手順です。

1. WAVを `assets/samples/` に置きます。モノラル／ステレオのどちらも使用でき、ステレオは読み込み時にモノラル化されます。
2. `assets/samples/manifest.json` の `samples` に次のような項目を追加します。
3. アプリを再起動します。登録した複数の音程から、演奏する音に最も近いWAVが自動的に選ばれます。

```json
{
  "instrument": "marimba",
  "midi": 60,
  "file": "marimba_C4.wav",
  "url": "https://example.com/source",
  "license": "CC0-1.0",
  "authors": "制作者名",
  "sha256": "WAVファイルのSHA-256"
}
```

`instrument` は `bgm.py` の `INSTRUMENTS` にある内部名、`midi` はWAVが実際に鳴らす音程です。このアプリではC4＝60、C5＝72として扱います。SHA-256は次のコマンドで確認できます。

Windows（PowerShell）：

```powershell
Get-FileHash assets\samples\marimba_C4.wav -Algorithm SHA256
```

macOS（ターミナル）：

```bash
shasum -a 256 assets/samples/marimba_C4.wav
```

### 新しい楽器を追加する

例えば `piano` を追加する場合は、上記のWAVとマニフェスト登録に加えて次を変更します。

1. `bgm.py` の `INSTRUMENTS` に `"piano"` を追加します。
2. `app.py` の `SOUND_NAMES` に `"piano": "ピアノ（実音源）"` を追加します。
3. 各WAVを `manifest.json` へ `"instrument": "piano"` として登録します。
4. 最初からピアノを使う曲調が必要なら、`bgm.py` の `PRESETS` に追加します。
5. 仮想環境のPythonで `-m unittest -v test_bgm test_humming test_app_humming` を実行します。

`fetch_samples.py` は実行のたびに、同ファイルの `FILES` から `manifest.json` を作り直します。手作業で登録した項目は消えるため、再取得・他のパソコンへの配布にも対応させる場合は、取得元URLを固定して `fetch_samples.py` にも追加してください。`assets/samples/*.wav` はGit管理の対象外なので、WAVを置くだけではGitへのプッシュに含まれません。

追加音源は、再配布や商用利用を含む利用条件を事前に確認し、配布元URL・制作者・ライセンス・SHA-256を記録してください。音源自体の利用条件と、その音源から生成した曲の独自性や権利の保証は別の問題です。

## コマンドで作る

Windows（PowerShell）：

```powershell
.\.venv\Scripts\python.exe bgm.py --preset "明るい散歩道" --seed 42 --bars 8 --out outputs\walk --mp3
.\.venv\Scripts\python.exe bgm.py --song outputs\walk\song.json --bpm 110 --out outputs\walk_slow
.\.venv\Scripts\python.exe bgm.py --hum "C:\path\鼻歌.wav" --hum-bars 2 --hum-grid 0.25 --out outputs\my_humming --mp3
.\.venv\Scripts\python.exe -m unittest -v test_bgm test_humming test_app_humming
```

macOS（ターミナル）：

```bash
./.venv/bin/python bgm.py --preset "明るい散歩道" --seed 42 --bars 8 --out outputs/walk --mp3
./.venv/bin/python bgm.py --song outputs/walk/song.json --bpm 110 --out outputs/walk_slow
./.venv/bin/python bgm.py --hum "/path/to/鼻歌.wav" --hum-bars 2 --hum-grid 0.25 --out outputs/my_humming --mp3
./.venv/bin/python -m unittest -v test_bgm test_humming test_app_humming
```

`song.json` の `parts.bass.gain` などを変更すると音量を調整できます。音符は `beat`（拍位置）、`duration`（拍単位の長さ）、`degree`（現在の調の音階度数、0始まり）、`octave`（C4=60）、`velocity`（0〜1）で表現しています。半音の補正は省略可能な `accidental`（-1/0/1）に保存します。パートの再生成回数は `revision` に記録します。

鼻歌の音程検出は[YIN法（de Cheveigné & Kawahara, 2002）](https://doi.org/10.1121/1.1458024)の差分関数に基づく独自実装です。

## 音源の出典

[VSCO 2 Community Edition](https://github.com/sgossner/VSCO-2-CE) / Sam Gossner & Simon Dalzell、サンプル編集 Elan Hickler/Soundemote。音源はCC0-1.0。上流コミットを固定して取得し、SHA-256を `assets/samples/manifest.json` に記録しています。ライセンス本文は同じフォルダの `VSCO-LICENSE.txt` にあります。再取得時・読み込み時にハッシュを確認します。

動画は着想元です。このフォルダは独自実装で、動画の有料キットのコード・サンプル曲・キャラクターボイスは含みません。
