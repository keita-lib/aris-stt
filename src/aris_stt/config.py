"""設定ファイル（%APPDATA%\\aris-stt\\config.toml）の読み込み。無ければ既定値で作る。"""

import json
import os
import re
import tomllib
from dataclasses import dataclass, field

APP_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "aris-stt")
CONFIG_PATH = os.path.join(APP_DIR, "config.toml")
LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "aris-stt")
LOG_PATH = os.path.join(LOG_DIR, "aris-stt.log")

# Ctrl+Vが文字の貼り付けにならないアプリ（VS Codeのターミナル上のCLI等）。Shift+Insertで貼る
DEFAULT_TERMINAL_APPS = ["code.exe", "cursor.exe", "windowsterminal.exe", "conhost.exe", "openconsole.exe"]


# 既定のキー。日本語キーボードの無変換と、無変換の無いキーボード（英語配列など）でも押せる Ctrl+Alt+Space の両方
DEFAULT_HOTKEYS = ["muhenkan", "ctrl+alt+space"]


def _default_text() -> str:
    return f'''# ARIS STT の設定。変更したら、トレイのメニューから「再起動」を選ぶと反映される。

# 録音開始・確定のキー。単独キー（muhenkan, henkan, f1〜f24, pause, scroll_lock など）か、
# 修飾キー付き（ctrl+alt+space, alt+q など）。["muhenkan", "f9"] のように複数並べると、どれでも使える。
# 取り消しは「shift+このキー」または Esc。
hotkey = {DEFAULT_HOTKEYS!r}

# 認識する言語（ja, en など）
language = "ja"

# モデル。auto = GPUがあれば large-v3、無ければ small。tiny / base / small / medium / large-v3 / large-v3-turbo も指定できる
model = "auto"

# 計算に使う装置。auto / cuda / cpu
device = "auto"

# 固有名詞の認識や句読点を安定させるためのヒント。よく使う単語を並べておくとよい
initial_prompt = "こんにちは。今日は、よろしくお願いします。"

# 話している間の字幕を更新する間隔（秒）
partial_interval = 0.6

# Ctrl+V ではなく Shift+Insert で貼り付けるアプリ（実行ファイル名）
terminal_apps = {DEFAULT_TERMINAL_APPS!r}
'''.replace("'", '"')


@dataclass
class Config:
    hotkey: str | list = field(default_factory=lambda: list(DEFAULT_HOTKEYS))  # 1つなら文字列、複数ならリスト
    language: str = "ja"
    model: str = "auto"
    device: str = "auto"
    initial_prompt: str = ""
    partial_interval: float = 0.6
    terminal_apps: list = field(default_factory=lambda: list(DEFAULT_TERMINAL_APPS))

    @property
    def hotkeys(self) -> list:
        return [self.hotkey] if isinstance(self.hotkey, str) else list(self.hotkey)

    @property
    def hotkey_label(self) -> str:
        """画面に出す表記（例: muhenkan / ctrl+alt+space）"""
        return " / ".join(self.hotkeys)


def save_hotkeys(hotkeys: list) -> None:
    """設定ファイルの hotkey の行だけを書き換える（他の行やコメントはそのまま残す）"""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        text = f.read()
    line = "hotkey = " + json.dumps(hotkeys, ensure_ascii=False)
    pattern = re.compile(r"^hotkey\s*=.*$", re.MULTILINE)
    text = pattern.sub(lambda m: line, text, count=1) if pattern.search(text) else line + "\n" + text
    with open(CONFIG_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def load() -> Config:
    os.makedirs(APP_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(_default_text())
    with open(CONFIG_PATH, "rb") as f:
        data = tomllib.load(f)
    cfg = Config()
    for k, v in data.items():
        if hasattr(cfg, k):
            setattr(cfg, k, v)
    cfg.terminal_apps = [a.lower() for a in cfg.terminal_apps]
    return cfg
