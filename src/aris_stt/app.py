"""ARIS STT 本体：ホットキーで録音し、字幕で途中経過を見せ、確定後にカーソル位置へ書き込む。"""

import glob
import os
import queue
import site
import subprocess
import sys
import threading
import time
import tkinter as tk
import winsound

import numpy as np
import sounddevice as sd

from . import __version__, config, settings, winapi

SAMPLE_RATE = 16000
PARTIAL_WINDOW_SEC = 30  # 途中経過は直近この秒数だけを読む（長い発話で重くならないように）


def log(message: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}"
    if sys.stdout:
        print(line, flush=True)
    os.makedirs(config.LOG_DIR, exist_ok=True)
    with open(config.LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def add_cuda_dll_dirs() -> None:
    """pipで入れたNVIDIAのライブラリ（cuBLAS等）を読み込めるようにする"""
    if getattr(sys, "frozen", False):
        roots = [sys._MEIPASS]  # exe版：同梱したDLLの場所
    else:
        roots = site.getsitepackages() + [site.getusersitepackages()]
    for root in roots:
        for d in glob.glob(os.path.join(root, "nvidia", "*", "bin")):
            os.add_dll_directory(d)
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")


# ---- 文字起こしワーカー ----
class Transcriber(threading.Thread):
    """モデル呼び出しはこのスレッドに集約する（同時呼び出しを避ける）"""

    def __init__(self, cfg: config.Config, events: queue.Queue):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.events = events
        self.jobs: queue.Queue = queue.Queue()
        self.model = None

    def _load(self):
        import ctranslate2
        from faster_whisper import WhisperModel
        from faster_whisper.utils import download_model

        device = self.cfg.device
        if device == "auto":
            device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        candidates = [device] if self.cfg.device != "auto" else ([device, "cpu"] if device == "cuda" else ["cpu"])
        last_error = None
        for dev in candidates:
            name = self.cfg.model if self.cfg.model != "auto" else ("large-v3" if dev == "cuda" else "small")
            try:
                download_model(name, local_files_only=True)
            except Exception:
                self.events.put(("status", f"モデル {name} をダウンロードしています（初回のみ。数分かかります）"))
            try:
                compute = "float16" if dev == "cuda" else "int8"
                model = WhisperModel(name, device=dev, compute_type=compute)
                # 初回推論のウォームアップ（1回目だけ極端に遅いため）
                list(model.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32), language=self.cfg.language)[0])
                return model, f"{name} / {dev}"
            except Exception as e:
                last_error = e
                log(f"{dev} での読み込みに失敗: {e}")
        raise RuntimeError(f"モデルを読み込めませんでした: {last_error}")

    def run(self):
        t0 = time.time()
        try:
            self.model, desc = self._load()
        except Exception as e:
            self.events.put(("fatal", str(e)))
            return
        self.events.put(("ready", f"{desc} 読み込み完了 ({time.time() - t0:.1f}s)"))
        while True:
            kind, session, audio = self.jobs.get()
            if kind == "partial" and not self.jobs.empty():
                continue  # 溜まった途中ジョブは最新だけ処理する
            text = self._transcribe(audio, beam_size=1 if kind == "partial" else 5)
            self.events.put((kind + "_result", (session, text)))

    def _transcribe(self, audio, beam_size):
        if len(audio) < SAMPLE_RATE * 0.3:
            return ""
        segments, _ = self.model.transcribe(
            audio, language=self.cfg.language, beam_size=beam_size, vad_filter=True,
            initial_prompt=self.cfg.initial_prompt or None, condition_on_previous_text=False,
        )
        return "".join(s.text for s in segments).strip()


# ---- 録音 ----
class Recorder:
    def __init__(self):
        self.chunks = []
        self.lock = threading.Lock()
        self.stream = None

    def start(self):
        self.chunks = []
        self.stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=self._callback)
        self.stream.start()

    def _callback(self, indata, frames, t, status):
        with self.lock:
            self.chunks.append(indata[:, 0].copy())

    def audio(self):
        with self.lock:
            return np.concatenate(self.chunks) if self.chunks else np.zeros(0, dtype=np.float32)

    def stop(self):
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        return self.audio()


# ---- 自動起動（スタートアップのショートカット） ----
STARTUP_LNK = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup", "ARIS STT.lnk")


def launch_command():
    """このアプリを起動し直すためのコマンド（exe版とPython版で異なる）"""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    exe = os.path.join(os.path.dirname(sys.executable), "aris-stt.exe")
    if os.path.exists(exe):  # uv tool のランチャー
        return [exe]
    return [sys.executable, "-m", "aris_stt"]


def autostart_enabled() -> bool:
    return os.path.exists(STARTUP_LNK)


def toggle_autostart(icon=None, item=None):
    if autostart_enabled():
        os.remove(STARTUP_LNK)
        log("自動起動を解除")
        return
    cmd = launch_command()
    target, args = cmd[0], " ".join(cmd[1:])
    # pywin32に頼らず、PowerShell経由でショートカットを作る
    ps = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK);"
        "$s.TargetPath=$env:TARGET;$s.Arguments=$env:ARGS;"
        "$s.Description='ARIS STT by Keita Nakamori / QUETTA ROBOTICS';$s.Save()"
    )
    env = dict(os.environ, LNK=STARTUP_LNK, TARGET=target, ARGS=args)
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], env=env, creationflags=0x08000000)
    log(f"自動起動を設定: {target} {args}")


# ---- タスクトレイ ----
def start_tray(events: queue.Queue):
    import pystray
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, 60, 60), fill=(60, 64, 90, 255))
    d.rounded_rectangle((24, 12, 40, 40), radius=8, fill=(240, 240, 245, 255))  # マイクの形
    d.arc((16, 22, 48, 48), 0, 180, fill=(240, 240, 245, 255), width=3)
    d.line((32, 48, 32, 54), fill=(240, 240, 245, 255), width=3)

    state = {"enabled": True}

    def toggle_enabled(icon, item):
        state["enabled"] = not state["enabled"]
        events.put(("enable" if state["enabled"] else "disable", None))

    menu = pystray.Menu(
        pystray.MenuItem("有効", toggle_enabled, checked=lambda item: state["enabled"]),
        pystray.MenuItem("⚙ 設定...", lambda: events.put(("settings", None)), default=True),
        pystray.MenuItem("設定ファイルを開く（詳しい設定）", lambda: os.startfile(config.CONFIG_PATH)),
        pystray.MenuItem("ログを開く", lambda: os.startfile(config.LOG_PATH)),
        pystray.MenuItem("ログオン時に自動起動", toggle_autostart, checked=lambda item: autostart_enabled()),
        pystray.MenuItem("再起動（設定を反映）", lambda: events.put(("restart", None))),
        pystray.MenuItem("終了", lambda: events.put(("quit", None))),
    )
    icon = pystray.Icon("aris-stt", img, f"ARIS STT {__version__}", menu)
    icon.run_detached()
    return icon


# ---- 字幕オーバーレイと状態管理 ----
class App:
    def __init__(self, cfg: config.Config):
        self.cfg = cfg
        self.events: queue.Queue = queue.Queue()
        self.hotkeys = winapi.HotkeyThread(self.events, [winapi.parse_hotkey(k) for k in cfg.hotkeys])
        self.worker = Transcriber(cfg, self.events)
        self.recorder = Recorder()
        self.state = "loading"  # loading / idle / recording / finalizing / disabled
        self.session = 0
        self.last_partial = 0.0
        self.target_hwnd = None
        self.tray = None
        self.settings_window = None

        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.92)
        self.root.configure(bg="#1e1e24")
        self.status = tk.Label(self.root, text="", fg="#9aa0b4", bg="#1e1e24", font=("Yu Gothic UI", 10), anchor="w")
        self.status.pack(fill="x", padx=14, pady=(8, 0))
        self.label = tk.Label(self.root, text="", fg="#f2f2f5", bg="#1e1e24", font=("Yu Gothic UI", 15),
                              justify="left", anchor="w", wraplength=760)
        self.label.pack(fill="both", padx=14, pady=(2, 12))
        self.root.update_idletasks()
        winapi.make_noactivate(winapi.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id())
        self.root.withdraw()

    def show(self, status, text=""):
        self.status.config(text=status)
        self.label.config(text=text or "…")
        self.root.update_idletasks()
        w, h = 800, max(self.root.winfo_reqheight(), 70)
        rect = winapi.window_rect(winapi.foreground_window())
        if rect:
            l, t, r, b = rect
            x, y = (l + r) // 2 - w // 2, b - h - 60
        else:
            x, y = self.root.winfo_screenwidth() // 2 - w // 2, self.root.winfo_screenheight() - h - 120
        self.root.geometry(f"{w}x{h}+{max(x, 0)}+{max(y, 0)}")
        self.root.deiconify()

    def hide(self):
        self.root.withdraw()

    def flash(self, status, text="", ms=2500):
        self.show(status, text)
        self.root.after(ms, lambda: self.state in ("idle", "disabled") and self.hide())

    # ---- 状態遷移 ----
    def start_recording(self):
        self.session += 1
        self.target_hwnd = winapi.foreground_window()
        try:
            self.recorder.start()
        except Exception as e:
            self.flash(f"マイクを開けませんでした: {e}", ms=4000)
            return
        self.state = "recording"
        self.hotkeys.post(winapi.WM_REG_CANCEL)
        winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
        self.show(f"● 録音中　{self.cfg.hotkey_label} で確定 / Esc で取り消し")

    def finish_recording(self):
        audio = self.recorder.stop()
        self.hotkeys.post(winapi.WM_UNREG_CANCEL)
        self.state = "finalizing"
        self.status.config(text="確定中…")
        self.worker.jobs.put(("final", self.session, audio))

    def cancel_recording(self):
        self.recorder.stop()
        self.hotkeys.post(winapi.WM_UNREG_CANCEL)
        self.session += 1  # 処理中の結果を捨てる
        self.state = "idle"
        self.hide()

    def commit(self, text):
        self.state = "idle"
        self.hide()
        if not text:
            return
        # 録音中にフォーカスが移っていたら元のウィンドウへ戻す
        if self.target_hwnd and winapi.foreground_window() != self.target_hwnd:
            winapi.user32.SetForegroundWindow(self.target_hwnd)
            time.sleep(0.05)
        exe = winapi.window_exe(winapi.foreground_window())
        method = winapi.paste_text(text, exe, self.cfg.terminal_apps)
        log(f"[確定] {text}  → {exe or '?'} ({method})")

    def open_settings(self):
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.lift()
            self.settings_window.focus_force()
            return
        if self.state == "recording":
            self.cancel_recording()
        self.settings_window = settings.SettingsWindow(
            self.root, self.cfg.hotkeys, self.apply_hotkeys, self.hotkeys, lambda: self.state != "disabled")

    def apply_hotkeys(self, hotkeys: list):
        config.save_hotkeys(hotkeys)
        self.cfg.hotkey = list(hotkeys)
        self.hotkeys.set_keys([winapi.parse_hotkey(k) for k in hotkeys])

    def quit(self, restart=False):
        if self.tray:
            self.tray.stop()
        self.root.destroy()
        if restart:
            subprocess.Popen(launch_command() + ["--wait-previous"], close_fds=True)

    def tick(self):
        try:
            while True:
                name, payload = self.events.get_nowait()
                if name == "ready":
                    self.state = "idle"
                    log(payload)
                    self.flash(f"ARIS STT 準備完了　{self.cfg.hotkey_label} で話す", payload)
                elif name == "status":
                    log(payload)
                    self.show("ARIS STT 起動中…", payload)
                elif name == "warn":
                    log(payload)
                    self.flash("ARIS STT", payload, ms=4000)
                elif name in ("error", "fatal"):
                    log(payload)
                    self.show(f"ARIS STT エラー（ログ: {config.LOG_PATH}）", payload)
                elif name == "settings":
                    self.open_settings()
                elif name == "hotkeys_applied":
                    failed = [self.cfg.hotkeys[i] for i in payload]
                    if failed:
                        msg = f"このキーは他のアプリが使っていて登録できませんでした: {', '.join(failed)}"
                        log(msg)
                        self.flash("ARIS STT", msg, ms=5000)
                    else:
                        log(f"ホットキーを変更: {self.cfg.hotkey_label}")
                        self.flash(f"ARIS STT　{self.cfg.hotkey_label} で話す", "キーの設定を反映しました")
                elif name == "quit":
                    return self.quit()
                elif name == "restart":
                    return self.quit(restart=True)
                elif name == "disable":
                    if self.state == "recording":
                        self.cancel_recording()
                    self.hotkeys.post(winapi.WM_UNREG_MAIN)
                    self.state = "disabled"
                    self.flash("ARIS STT 一時停止中")
                elif name == "enable" and self.state == "disabled":
                    self.hotkeys.post(winapi.WM_REG_MAIN)
                    self.state = "idle"
                    self.flash(f"ARIS STT 有効　{self.cfg.hotkey_label} で話す")
                elif name == "toggle":
                    if self.state == "idle":
                        self.start_recording()
                    elif self.state == "recording":
                        self.finish_recording()
                elif name == "cancel" and self.state == "recording":
                    self.cancel_recording()
                elif name == "partial_result":
                    session, text = payload
                    if session == self.session and self.state == "recording":
                        self.show(self.status.cget("text"), text)
                elif name == "final_result":
                    session, text = payload
                    if session == self.session and self.state == "finalizing":
                        self.commit(text)
        except queue.Empty:
            pass

        if self.state == "recording" and time.time() - self.last_partial >= self.cfg.partial_interval:
            self.last_partial = time.time()
            audio = self.recorder.audio()[-SAMPLE_RATE * PARTIAL_WINDOW_SEC:]
            self.worker.jobs.put(("partial", self.session, audio))
        self.root.after(50, self.tick)

    def run(self):
        self.hotkeys.start()
        self.worker.start()
        try:
            self.tray = start_tray(self.events)
        except Exception as e:
            log(f"トレイアイコンを作れませんでした: {e}")
        self.show("ARIS STT 起動中…", "モデルを読み込んでいます")
        self.root.after(50, self.tick)
        self.root.mainloop()


def main():
    import ctypes
    # 高DPI環境で座標がずれないようにする
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    if sys.stdout:  # pythonw起動時はstdoutが無い
        sys.stdout.reconfigure(encoding="utf-8")
    # 再起動時は、前のプロセスが終わるまで少し待つ
    tries = 50 if "--wait-previous" in sys.argv else 1
    for _ in range(tries):
        if winapi.single_instance("Local\\aris-stt"):
            break
        time.sleep(0.1)
    else:
        return  # すでに起動している
    add_cuda_dll_dirs()
    try:
        cfg = config.load()
    except Exception as e:
        log(f"設定ファイルを読めませんでした（{config.CONFIG_PATH}）: {e}")
        raise
    log(f"ARIS STT {__version__} 起動（hotkey={cfg.hotkey_label}, model={cfg.model}, device={cfg.device}）")
    App(cfg).run()
