"""設定画面（トレイの「⚙ 設定...」から開く）：話し始め・確定のキーを、実際に押して登録する。"""

import tkinter as tk
from tkinter import messagebox, ttk

from . import config, winapi

# 画面に出すときの呼び方
DISPLAY_NAMES = {
    "muhenkan": "無変換", "henkan": "変換", "kana": "かな", "space": "Space", "tab": "Tab",
    "pause": "Pause", "scroll_lock": "Scroll Lock", "insert": "Insert", "home": "Home", "end": "End",
    "pageup": "Page Up", "pagedown": "Page Down", "`": "`",
    "ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Win",
}
# 修飾キー無しで割り当てると、普段の文字入力ができなくなるキー
TYPING_KEYS = {chr(c) for c in range(ord("a"), ord("z") + 1)} | {str(d) for d in range(10)} | {"space", "tab", "`"}
VK_ESCAPE = 0x1B


def display(hotkey: str) -> str:
    return " + ".join(DISPLAY_NAMES.get(p, p.upper()) for p in hotkey.split("+"))


class SettingsWindow(tk.Toplevel):
    def __init__(self, root, hotkeys: list, on_save, hotkey_thread: winapi.HotkeyThread, is_enabled):
        super().__init__(root)
        self.on_save = on_save
        self.hotkey_thread = hotkey_thread
        self.is_enabled = is_enabled
        self.keys = list(hotkeys)
        self.capture = None

        self.title("ARIS STT 設定")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        pad = {"padx": 16}

        ttk.Label(self, text="話し始める・確定するキー", font=("Yu Gothic UI", 11, "bold")).pack(anchor="w", pady=(14, 2), **pad)
        ttk.Label(self, text="登録したキーのどれを押しても使えます。キーボードを付け替える場合は、両方のキーを登録しておくと便利です。",
                  wraplength=420, foreground="#555").pack(anchor="w", **pad)

        body = ttk.Frame(self)
        body.pack(fill="x", pady=8, **pad)
        self.listbox = tk.Listbox(body, height=5, width=32, font=("Yu Gothic UI", 11), activestyle="none")
        self.listbox.pack(side="left", fill="y")
        side = ttk.Frame(body)
        side.pack(side="left", fill="y", padx=(10, 0))
        self.add_btn = ttk.Button(side, text="キーを追加...", command=self.start_capture)
        self.add_btn.pack(fill="x")
        ttk.Button(side, text="削除", command=self.remove).pack(fill="x", pady=4)
        ttk.Button(side, text="既定に戻す", command=self.reset).pack(fill="x")

        self.hint = ttk.Label(self, text="", foreground="#0a58ca", wraplength=420)
        self.hint.pack(anchor="w", **pad)
        ttk.Label(self, text="取り消しは Esc、または Shift + 登録したキー（録音中のみ）。\n"
                             "言語やモデルなどの詳しい設定は、トレイの「設定ファイルを開く」から変えられます。",
                  foreground="#777", wraplength=420).pack(anchor="w", pady=(6, 0), **pad)

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", pady=14, **pad)
        ttk.Button(bottom, text="キャンセル", command=self.close).pack(side="right")
        ttk.Button(bottom, text="保存", command=self.save).pack(side="right", padx=6)

        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda e: self.capture is None and self.close())
        self.refresh()
        self.update_idletasks()
        x = self.winfo_screenwidth() // 2 - self.winfo_reqwidth() // 2
        y = self.winfo_screenheight() // 3 - self.winfo_reqheight() // 2
        self.geometry(f"+{x}+{y}")
        self.focus_force()

    def refresh(self):
        self.listbox.delete(0, "end")
        for k in self.keys:
            self.listbox.insert("end", "  " + display(k))

    # ---- キーの登録 ----
    def start_capture(self):
        if self.capture is not None:
            return
        # 登録済みのキーを押しても録音が始まらないよう、読み取りの間はホットキーを外す
        self.hotkey_thread.post(winapi.WM_UNREG_MAIN)
        self.capture = winapi.KeyCapture(lambda mods, vk: self.after(0, self.on_key, mods, vk))
        if not self.capture.start():
            self.capture = None
            self._restore_hotkeys()
            messagebox.showerror("ARIS STT", "キーを読み取れませんでした", parent=self)
            return
        self.add_btn.configure(state="disabled")
        self.hint.configure(text="登録したいキーを押してください（Ctrl・Alt などと組み合わせてもOK）。Esc で取り消し")

    def stop_capture(self):
        if self.capture is not None:
            self.capture.stop()
            self.capture = None
            self._restore_hotkeys()
        self.add_btn.configure(state="normal")

    def _restore_hotkeys(self):
        if self.is_enabled():
            self.hotkey_thread.post(winapi.WM_REG_MAIN)

    def on_key(self, mods: int, vk: int):
        if self.capture is None:
            return
        self.stop_capture()
        if vk == VK_ESCAPE and not mods:
            self.hint.configure(text="")
            return
        name = winapi.format_hotkey(mods, vk)
        if name is None:
            self.hint.configure(text="このキーは使えません。別のキーを選んでください")
            return
        if not mods & (winapi.MOD_CONTROL | winapi.MOD_ALT | winapi.MOD_WIN) and name.split("+")[-1] in TYPING_KEYS:
            self.hint.configure(text=f"「{display(name)}」だけだと普段の文字入力ができなくなります。Ctrl や Alt と組み合わせてください")
            return
        if name in self.keys:
            self.hint.configure(text=f"「{display(name)}」はもう登録されています")
            return
        self.keys.append(name)
        self.refresh()
        self.hint.configure(text=f"「{display(name)}」を追加しました。「保存」で反映されます")

    # ---- 一覧の操作 ----
    def remove(self):
        sel = self.listbox.curselection()
        if not sel:
            self.hint.configure(text="削除するキーを一覧から選んでください")
            return
        del self.keys[sel[0]]
        self.refresh()

    def reset(self):
        self.keys = list(config.DEFAULT_HOTKEYS)
        self.refresh()
        self.hint.configure(text="既定のキーに戻しました。「保存」で反映されます")

    def save(self):
        if not self.keys:
            messagebox.showwarning("ARIS STT", "キーを1つ以上登録してください", parent=self)
            return
        try:
            self.on_save(self.keys)
        except Exception as e:
            messagebox.showerror("ARIS STT", f"保存できませんでした: {e}", parent=self)
            return
        self.close()

    def close(self):
        self.stop_capture()
        self.destroy()
