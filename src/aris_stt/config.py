"""設定ファイル（%APPDATA%\\aris-stt\\config.toml）の読み込み。無ければ既定値で作る。"""

import ctypes
import os
import tomllib
from dataclasses import dataclass, field

APP_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "aris-stt")
CONFIG_PATH = os.path.join(APP_DIR, "config.toml")
LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "aris-stt")
LOG_PATH = os.path.join(LOG_DIR, "aris-stt.log")

# Ctrl+Vが文字の貼り付けにならないアプリ（VS Codeのターミナル上のCLI等）。Shift+Insertで貼る
DEFAULT_TERMINAL_APPS = ["code.exe", "cursor.exe", "windowsterminal.exe", "conhost.exe", "openconsole.exe"]


def _is_japanese_keyboard() -> bool:
    try:
        return ctypes.windll.user32.GetKeyboardType(0) == 7
    except Exception:
        return False


def _default_text() -> str:
    hotkey = "muhenkan" if _is_japanese_keyboard() else "ctrl+alt+space"
    return f'''# ARIS STT の設定。変更したら、トレイのメニューから「再起動」を選ぶと反映される。

# 録音開始・確定のキー。単独キー（muhenkan, henkan, f1〜f24, pause, scroll_lock など）か、
# 修飾キー付き（ctrl+alt+space, alt+q など）。取り消しは「shift+このキー」または Esc。
hotkey = "{hotkey}"

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
    hotkey: str = "muhenkan"
    language: str = "ja"
    model: str = "auto"
    device: str = "auto"
    initial_prompt: str = ""
    partial_interval: float = 0.6
    terminal_apps: list = field(default_factory=lambda: list(DEFAULT_TERMINAL_APPS))


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
