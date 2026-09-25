"""모니터 작업 영역과 클릭이 통과하는 창 (Win32)."""
import ctypes
from ctypes import wintypes

KEY = "#010101"        # 창에서 투명하게 뚫을 색
GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_NOACTIVATE = -20, 0x80000, 0x20, 0x08000000


def work_area():
    rect = wintypes.RECT()
    ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
    return rect.left, rect.top, rect.right, rect.bottom


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


MONITORENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC,
                                     ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)


def monitors():
    """모든 모니터의 작업 영역(작업 표시줄 제외)을 왼쪽부터 차례로."""
    found = []

    def collect(hmon, hdc, lprc, lparam):
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            w = mi.rcWork
            found.append((w.left, w.top, w.right, w.bottom))
        return 1

    try:
        ctypes.windll.user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(collect), 0)
    except Exception:
        pass
    return sorted(found) or [work_area()]


def monitor_at(x, y):
    """그 점이 있는 모니터. 화면 밖이면(모니터를 뺐거나 배치가 바뀌면) 가장 가까운 모니터."""
    ms = monitors()
    for m in ms:
        if m[0] <= x < m[2] and m[1] <= y < m[3]:
            return m
    return min(ms, key=lambda m: max(m[0] - x, 0, x - m[2]) ** 2 + max(m[1] - y, 0, y - m[3]) ** 2)


def click_through(w):
    """창 위에서도 마우스가 아래 창으로 통과하고, 포커스를 빼앗지 않게 한다."""
    try:
        u = ctypes.windll.user32
        u.GetParent.argtypes, u.GetParent.restype = [wintypes.HWND], wintypes.HWND
        u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        u.GetWindowLongW.restype = wintypes.LONG
        u.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
        u.SetWindowLongW.restype = wintypes.LONG
        hwnd = wintypes.HWND(u.GetParent(wintypes.HWND(w.winfo_id())) or w.winfo_id())
        ex = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
        u.SetWindowLongW(hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE)
    except Exception:
        pass
