"""Win32 API まわり（ホットキー、キー送信、クリップボード、ウィンドウ情報）。"""

import ctypes
import ctypes.wintypes as wt
import os
import queue
import threading
import time

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY, WM_USER = 0x0312, 0x0400
INPUT_KEYBOARD, KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP = 1, 0x0001, 0x0002
VK_SHIFT, VK_CONTROL, VK_INSERT, VK_V, VK_ESCAPE = 0x10, 0x11, 0x2D, 0x56, 0x1B

KEY_NAMES = {
    "muhenkan": 0x1D, "henkan": 0x1C, "kana": 0x15, "space": 0x20, "tab": 0x09,
    "pause": 0x13, "scroll_lock": 0x91, "insert": 0x2D, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22, "`": 0xC0, "backquote": 0xC0,
}
KEY_NAMES.update({f"f{i}": 0x6F + i for i in range(1, 25)})
KEY_NAMES.update({chr(c): c for c in range(ord("A"), ord("Z") + 1)})
KEY_NAMES.update({chr(c).lower(): c for c in range(ord("A"), ord("Z") + 1)})
KEY_NAMES.update({str(d): 0x30 + d for d in range(10)})
MOD_NAMES = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT, "win": MOD_WIN}


def parse_hotkey(text: str):
    """'ctrl+alt+space' や 'muhenkan' を (修飾キー, 仮想キー) にする"""
    mods, vk = 0, None
    for part in text.lower().replace(" ", "").split("+"):
        if part in MOD_NAMES:
            mods |= MOD_NAMES[part]
        elif part in KEY_NAMES:
            vk = KEY_NAMES[part]
        else:
            raise ValueError(f"不明なキー名: {part}")
    if vk is None:
        raise ValueError(f"キーが指定されていません: {text}")
    return mods, vk


# 仮想キー → 設定ファイルに書く名前（"`" と "backquote" のような別名は先に書いた方を使う）
VK_NAMES = {}
for _name, _vk in KEY_NAMES.items():
    VK_NAMES.setdefault(_vk, _name)


def format_hotkey(mods: int, vk: int) -> str | None:
    """(修飾キー, 仮想キー) を 'ctrl+alt+space' の形にする。設定で扱えないキーなら None"""
    name = VK_NAMES.get(vk)
    if name is None:
        return None
    parts = [n for n, m in (("ctrl", MOD_CONTROL), ("alt", MOD_ALT), ("shift", MOD_SHIFT), ("win", MOD_WIN)) if mods & m]
    return "+".join(parts + [name.lower()])


# ---- キー送信 ----
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _INPUTUNION(ctypes.Union):
    # MOUSEINPUTが最大サイズなので、構造体サイズを合わせるための詰め物
    _fields_ = [("ki", KEYBDINPUT), ("_pad", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wt.DWORD), ("u", _INPUTUNION)]


def _send_keys(seq) -> None:
    inputs = []
    for vk, flags in seq:
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.u.ki = KEYBDINPUT(vk, user32.MapVirtualKeyW(vk, 0), flags, 0, 0)
        inputs.append(inp)
    arr = (INPUT * len(inputs))(*inputs)
    user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


def send_ctrl_v() -> None:
    _send_keys(((VK_CONTROL, 0), (VK_V, 0), (VK_V, KEYEVENTF_KEYUP), (VK_CONTROL, KEYEVENTF_KEYUP)))


def send_shift_insert() -> None:
    # EXTENDEDKEYを付けないとテンキーの0扱いになる
    ext = KEYEVENTF_EXTENDEDKEY
    _send_keys(((VK_SHIFT, 0), (VK_INSERT, ext), (VK_INSERT, ext | KEYEVENTF_KEYUP), (VK_SHIFT, KEYEVENTF_KEYUP)))


# ---- クリップボード ----
CF_UNICODETEXT, GMEM_MOVEABLE = 13, 0x0002
kernel32.GlobalAlloc.restype = wt.HGLOBAL
kernel32.GlobalAlloc.argtypes = [wt.UINT, ctypes.c_size_t]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [wt.HGLOBAL]
kernel32.GlobalUnlock.argtypes = [wt.HGLOBAL]
user32.SetClipboardData.restype = wt.HANDLE
user32.SetClipboardData.argtypes = [wt.UINT, wt.HANDLE]
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]


def set_clipboard_text(text: str) -> bool:
    # 他アプリが一瞬掴んでいることがあるので少しだけ粘る
    for _ in range(20):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.01)
    else:
        return False
    try:
        user32.EmptyClipboard()
        buf = ctypes.create_unicode_buffer(text)
        size = ctypes.sizeof(buf)
        h = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
        p = kernel32.GlobalLock(h)
        ctypes.memmove(p, buf, size)
        kernel32.GlobalUnlock(h)
        user32.SetClipboardData(CF_UNICODETEXT, h)  # 成功後の解放はOSが持つ
        return True
    finally:
        user32.CloseClipboard()


def paste_text(text: str, exe: str, terminal_apps) -> str:
    """クリップボード経由で貼り付ける。
    1文字ずつのUnicode送信はターミナルで文字が重複・欠落したため、貼り付けに統一している。
    クリップボードは元に戻さない（VS Codeは読み取りが遅く、戻すと古い内容が貼られるため）"""
    if not set_clipboard_text(text):
        return "クリップボード設定失敗"
    time.sleep(0.05)
    if exe.lower() in terminal_apps:
        send_shift_insert()
        return "Shift+Insert"
    send_ctrl_v()
    return "Ctrl+V"


# ---- ウィンドウ ----
def foreground_window():
    return user32.GetForegroundWindow()


def window_exe(hwnd) -> str:
    if not hwnd:
        return ""
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(512)
        n = wt.DWORD(512)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return os.path.basename(buf.value)
        return ""
    finally:
        kernel32.CloseHandle(h)


def window_rect(hwnd):
    r = wt.RECT()
    if hwnd and user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return r.left, r.top, r.right, r.bottom
    return None


def make_noactivate(hwnd) -> None:
    """字幕ウィンドウが入力先のフォーカスを奪わないようにする"""
    GWL_EXSTYLE = -20
    WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW, WS_EX_TOPMOST = 0x08000000, 0x00000080, 0x00000008
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST)


def single_instance(name: str) -> bool:
    """同じアプリが既に動いていれば False"""
    kernel32.CreateMutexW.restype = wt.HANDLE
    h = kernel32.CreateMutexW(None, False, name)
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        # 開いたハンドルを残すと、前のプロセスが終わってもミューテックスが消えないため閉じる
        kernel32.CloseHandle(h)
        return False
    return True  # ハンドルはプロセス終了まで保持する


# ---- ホットキー（専用スレッドでメッセージループを回す） ----
# 録音開始・確定のキーは HK_TOGGLE + i、その Shift 版（取り消し）は HK_CANCEL_SHIFT + i で登録する（i は何番目のキーか）
HK_CANCEL_ESC, HK_TOGGLE, HK_CANCEL_SHIFT = 1, 100, 200
WM_REG_CANCEL, WM_UNREG_CANCEL, WM_REG_MAIN, WM_UNREG_MAIN = WM_USER + 1, WM_USER + 2, WM_USER + 3, WM_USER + 4
WM_SET_KEYS = WM_USER + 5


class HotkeyThread(threading.Thread):
    def __init__(self, events: queue.Queue, keys: list):
        """keys: parse_hotkey の結果 (修飾キー, 仮想キー) のリスト"""
        super().__init__(daemon=True)
        self.events = events
        self.keys = keys
        self.new_keys = None  # set_keys で差し替える予定のキー
        self.thread_id = None
        self.ready = threading.Event()

    def _register_main(self) -> list:
        """登録できなかったキーの番号を返す"""
        return [i for i, (mods, vk) in enumerate(self.keys)
                if not user32.RegisterHotKey(None, HK_TOGGLE + i, mods | MOD_NOREPEAT, vk)]

    def run(self):
        self.thread_id = kernel32.GetCurrentThreadId()
        failed = self._register_main()
        if len(failed) == len(self.keys):
            self.events.put(("error", "ホットキーを登録できませんでした（他のアプリが使っている可能性があります）"))
        elif failed:
            self.events.put(("warn", f"一部のホットキーを登録できませんでした（{len(failed)}個）。他のキーは使えます"))
        self.ready.set()
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            m = msg.message
            if m == WM_HOTKEY:
                is_toggle = HK_TOGGLE <= msg.wParam < HK_TOGGLE + len(self.keys)
                self.events.put(("toggle" if is_toggle else "cancel", None))
            elif m == WM_REG_CANCEL:
                # 取り消しキーは録音中だけ奪う（常時登録すると他アプリのEscが効かなくなる）
                user32.RegisterHotKey(None, HK_CANCEL_ESC, MOD_NOREPEAT, VK_ESCAPE)
                for i, (mods, vk) in enumerate(self.keys):
                    if not mods & MOD_SHIFT:
                        user32.RegisterHotKey(None, HK_CANCEL_SHIFT + i, mods | MOD_SHIFT | MOD_NOREPEAT, vk)
            elif m == WM_UNREG_CANCEL:
                user32.UnregisterHotKey(None, HK_CANCEL_ESC)
                for i in range(len(self.keys)):
                    user32.UnregisterHotKey(None, HK_CANCEL_SHIFT + i)
            elif m == WM_REG_MAIN:
                self._register_main()
            elif m == WM_UNREG_MAIN:
                self._unregister_main()
            elif m == WM_SET_KEYS:
                # 設定画面で変えたキーに差し替える（再起動なしで反映）
                self._unregister_main()
                self.keys = self.new_keys
                failed = self._register_main()
                self.events.put(("hotkeys_applied", failed))

    def _unregister_main(self) -> None:
        for i in range(len(self.keys)):
            user32.UnregisterHotKey(None, HK_TOGGLE + i)

    def set_keys(self, keys: list) -> None:
        self.new_keys = keys
        self.post(WM_SET_KEYS)

    def post(self, message: int) -> None:
        self.ready.wait()
        user32.PostThreadMessageW(self.thread_id, message, 0, 0)


# ---- キーの読み取り（設定画面で「押したキーを登録する」ため） ----
# IME がオンでも無変換などを確実に拾えるよう、低レベルのキーボードフックで受け取る
WH_KEYBOARD_LL, WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP, WM_QUIT = 13, 0x0100, 0x0101, 0x0104, 0x0105, 0x0012
# 修飾キーの仮想キー（左右・共通）→ 修飾フラグ
_MOD_OF_VK = {0x11: MOD_CONTROL, 0xA2: MOD_CONTROL, 0xA3: MOD_CONTROL, 0x12: MOD_ALT, 0xA4: MOD_ALT, 0xA5: MOD_ALT,
              0x10: MOD_SHIFT, 0xA0: MOD_SHIFT, 0xA1: MOD_SHIFT, 0x5B: MOD_WIN, 0x5C: MOD_WIN}


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wt.DWORD), ("scanCode", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wt.WPARAM, wt.LPARAM)
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wt.HINSTANCE, wt.DWORD]
user32.SetWindowsHookExW.restype = wt.HHOOK
user32.CallNextHookEx.argtypes = [wt.HHOOK, ctypes.c_int, wt.WPARAM, wt.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [wt.HHOOK]
kernel32.GetModuleHandleW.restype = wt.HMODULE


class KeyCapture(threading.Thread):
    """修飾キー以外のキーが押されたら、そのキーを他のアプリに渡さずに on_key(mods, vk) を呼ぶ。
    フックは専用スレッドに入れる。tk のスレッドに入れると、tk が GIL を手放してイベントを待っている最中に
    フックの Python コードが割り込み、Fatal Python error（PyEval_RestoreThread）で落ちる。
    on_key もこのスレッドから呼ばれるので、tk には触らずキューに置くだけにすること"""

    def __init__(self, on_key):
        super().__init__(daemon=True)
        self.on_key = on_key
        self.hook = None
        self.down = set()  # 今押されている修飾キー
        self._proc = HOOKPROC(self._handle)  # 参照を保持しないと GC で消えて落ちる
        self.thread_id = None
        self.ready = threading.Event()

    def _handle(self, code, wparam, lparam):
        if code == 0:
            vk = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents.vkCode
            pressed = wparam in (WM_KEYDOWN, WM_SYSKEYDOWN)
            # 修飾キーの状態は、フックが見た上げ下げから自分で数える
            # （GetAsyncKeyState はフックの中だと直前のキーの状態が残っていることがある）
            if vk in _MOD_OF_VK:
                (self.down.add if pressed else self.down.discard)(vk)
            elif pressed:
                mods = 0
                for d in self.down:
                    mods |= _MOD_OF_VK[d]
                self.on_key(mods, vk)
                return 1  # 他のアプリには渡さない
        return user32.CallNextHookEx(self.hook, code, wparam, lparam)

    def run(self):
        self.thread_id = kernel32.GetCurrentThreadId()
        self.hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, kernel32.GetModuleHandleW(None), 0)
        self.ready.set()
        if not self.hook:
            return
        # フックの呼び出しは、このスレッドのメッセージループの中で行われる
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass
        user32.UnhookWindowsHookEx(self.hook)
        self.hook = None

    def begin(self) -> bool:
        """読み取りを始める。フックを入れられなければ False"""
        self.start()
        self.ready.wait(2)
        return bool(self.hook)

    def stop(self) -> None:
        if self.thread_id and self.is_alive():
            user32.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)

