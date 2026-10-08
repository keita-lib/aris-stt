# ARIS STT

**声で話すと、その場で文字になり、カーソルの位置に書き込まれる。** Windows 用の音声入力ツールです。

- キーを1回押して話し、もう1回押すと、話した内容がアクティブなウィンドウのカーソル位置に書き込まれます（メモ帳、ブラウザ、VS Code、ターミナルなど）
- 話している間は、画面下の字幕で認識の途中経過が見えます
- 音声認識（[faster-whisper](https://github.com/SYSTRAN/faster-whisper)）は手元の PC で動きます。声を外部のサービスに送りません
- NVIDIA の GPU があれば高精度の large-v3、無ければ CPU で small モデルを自動で使います

## インストール

入れ方は2通りあります。どちらも中身は同じです。

### A. exe 版（かんたん）

1. [Releases](https://github.com/keita-lib/aris-stt/releases/latest) から zip をダウンロードします
   - NVIDIA の GPU がある PC：`aris-stt-<version>-windows-gpu.zip`（約630MB）
   - それ以外の PC：`aris-stt-<version>-windows-cpu.zip`（約100MB）
2. 好きな場所に展開して、`aris-stt\aris-stt.exe` をダブルクリックします
3. ログオン時に自動で起動したい場合は、タスクトレイのマイクのアイコンを右クリックして「ログオン時に自動起動」にチェックを入れます

署名の無い exe のため、初回は Windows の「PC が保護されました」という警告が出ることがあります。「詳細情報」→「実行」で起動できます。

### B. コマンド1行（PowerShell）

PowerShell を開いて、次の1行を実行します。

```powershell
irm https://raw.githubusercontent.com/keita-lib/aris-stt/main/install.ps1 | iex
```

インストーラーが行うこと：

1. [uv](https://docs.astral.sh/uv/)（Python とパッケージの管理ツール）が無ければ入れる。Python を別に入れる必要はありません
2. NVIDIA の GPU があれば GPU 版、無ければ CPU 版の ARIS STT を入れる
3. スタートメニューと、ログオン時の自動起動にショートカットを作る
4. ARIS STT を起動する

初回の起動時に音声認識モデルをダウンロードします（GPU 版 約3GB / CPU 版 約0.5GB）。

## はじめての使い方（インストールしたら）

1. 画面右下のタスクトレイに、マイクのアイコンが出ます（見当たらないときは「^」を押して隠れたアイコンを開きます）
2. 画面下に「ARIS STT 準備完了」と出たら使えます。初回はモデルのダウンロードがあるので、数分かかることがあります
3. 文字を書き込みたい場所（メモ帳、ブラウザの入力欄、チャットなど）をクリックして、カーソルを置きます
4. **無変換**（または **Ctrl+Alt+Space**）を押すと「ポン」と鳴って録音が始まります。そのまま話してください。画面下の字幕に、認識の途中経過が出ます
5. 話し終わったら、もう一度同じキー（登録したキーならどれでも）を押します。少しして、話した内容がカーソルの位置に書き込まれます

やめたいときは、録音中に **Esc** を押すと、何も書き込まずに取り消せます。

うまく認識させるコツ：

- 一文ずつではなく、言いたいことをまとめて話しても大丈夫です。句読点も自動で付きます
- よく使う固有名詞や専門用語は、設定ファイルの `initial_prompt` に並べておくと、正しく書かれやすくなります
- 使わないときは、トレイのメニューの「有効」のチェックを外すと一時停止できます（キーが本来の働きに戻ります）

## 使い方

| 操作 | キー |
|---|---|
| 話し始める / 確定して書き込む | **無変換** または **Ctrl+Alt+Space**（どちらでも。設定画面で変えられます） |
| 取り消す（録音中のみ） | Shift+上のキー、または Esc |

タスクトレイのマイクのアイコンから、一時停止・設定・再起動・終了ができます。

### キーを変える（設定画面）

タスクトレイのマイクのアイコンを右クリックして「⚙ 設定...」を選びます（アイコンをクリックしても開きます）。

1. 「キーを追加...」を押して、使いたいキーを実際に押します（Ctrl・Alt・Shift・Win との組み合わせもできます）
2. いらないキーは一覧で選んで「削除」します
3. 「保存」を押すと、その場で反映されます（再起動は要りません）

キーはいくつでも登録できて、どれを押しても使えます。日本語キーボードと英語キーボードを付け替えて使う場合は、両方で押せるキーを登録しておくと便利です。

### 詳しい設定（設定ファイル）

`%APPDATA%\aris-stt\config.toml` を編集し、トレイのメニューから「再起動（設定を反映）」を選びます。

| 項目 | 内容 |
|---|---|
| `hotkey` | 話し始め・確定のキー（`muhenkan`、`f9`、`ctrl+alt+space`、`alt+q` など）。`["muhenkan", "f9"]` のように複数並べられます |
| `language` | 認識する言語（`ja`、`en` など） |
| `model` | `auto` / `tiny` / `base` / `small` / `medium` / `large-v3` / `large-v3-turbo` |
| `device` | `auto` / `cuda` / `cpu` |
| `initial_prompt` | よく使う固有名詞などのヒント。認識と句読点が安定します |
| `terminal_apps` | Ctrl+V ではなく Shift+Insert で貼り付けるアプリ |

### 知っておいてほしいこと

- 書き込みはクリップボード経由です。書き込むたびに、クリップボードの内容は認識した文で上書きされます
- 割り当てたキー（無変換など）の本来の働きは、ARIS STT の動作中は使えません
- ログ：`%LOCALAPPDATA%\aris-stt\aris-stt.log`

### 困ったとき

| 症状 | 対処 |
|---|---|
| キーを押しても録音が始まらない | 他のアプリが同じキーを使っている可能性があります。「⚙ 設定...」で別のキー（F9 や Ctrl+Alt+Space など）を追加してください |
| 書き込まれない（ターミナルなど） | Ctrl+V で貼り付けできないアプリは、設定ファイルの `terminal_apps` に実行ファイル名を足すと Shift+Insert で貼り付けます |
| 認識が遅い | GPU の無い PC では、設定ファイルの `model` を `base` や `tiny` にすると速くなります（精度は下がります） |
| 起動しない・すぐ終わる | ログ（上記）の最後のほうにエラーの内容が書かれています |

## 新しい版にする

- exe 版：トレイから終了し、[Releases](https://github.com/keita-lib/aris-stt/releases/latest) から新しい zip をダウンロードして、前のフォルダと入れ替えます
- コマンドで入れた場合：インストールと同じ1行をもう一度実行します

どちらも、設定（キーの登録など）はそのまま引き継がれます。

## アンインストール

exe 版は、トレイから終了して、展開したフォルダを削除します（自動起動にしていた場合は、先にチェックを外してください）。

コマンドで入れた場合は：

```powershell
irm https://raw.githubusercontent.com/keita-lib/aris-stt/main/uninstall.ps1 | iex
```

設定とログも消す場合は、先に `$env:ARIS_STT_PURGE = "1"` を実行してください。

## 動作環境

- Windows 10 / 11
- マイク
- GPU 版：NVIDIA の GPU（VRAM 6GB 以上を推奨）。CUDA Toolkit を別に入れる必要はありません

## ライセンス

**CC BY-ND 4.0（表示 - 改変禁止 4.0 国際）**

- 個人でも、会社でも、無料で使えます
- 使う・共有する・再配布するときは、作者の表記を必ず残してください：
  **ARIS STT by Keita Nakamori / QUETTA ROBOTICS**
- 改変したものを配布することはできません

詳しくは [LICENSE](LICENSE) と [NOTICE](NOTICE) を見てください。

---

## English

**ARIS STT** is a voice-input tool for Windows. Press a key, speak, press it again, and your words are written at the cursor in the active window. Live captions show the transcription as you speak. Speech recognition (faster-whisper) runs locally; your voice is never sent to an outside service. It uses large-v3 on an NVIDIA GPU, or the small model on CPU.

**Install**: download the zip from [Releases](https://github.com/keita-lib/aris-stt/releases/latest) (`-gpu` for NVIDIA GPUs, `-cpu` otherwise), extract it, and run `aris-stt.exe`. Or install with one line in PowerShell:

```powershell
irm https://raw.githubusercontent.com/keita-lib/aris-stt/main/install.ps1 | iex
```

**First use**: a microphone icon appears in the system tray. When "ARIS STT 準備完了" (ready) shows at the bottom of the screen, click where you want to type, press the key, speak, and press it again. The first launch downloads the speech model and may take a few minutes.

**Use**: press **Muhenkan** or **Ctrl+Alt+Space** to start and again to write the text. Shift+that key or Esc cancels. To change the keys, open the tray icon menu → "⚙ 設定..." (Settings) and press the key you want; several keys can be registered. Other settings: `%APPDATA%\aris-stt\config.toml`.

**Update**: download the new zip and replace the old folder, or run the install line again. Your settings are kept.

**Uninstall**:

```powershell
irm https://raw.githubusercontent.com/keita-lib/aris-stt/main/uninstall.ps1 | iex
```

**License**: CC BY-ND 4.0. Free for personal and commercial use. You must keep the attribution **"ARIS STT by Keita Nakamori / QUETTA ROBOTICS"**. You may not distribute modified versions.

Copyright (c) 2026 Keita Nakamori / QUETTA ROBOTICS
