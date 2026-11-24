"""Warm Retro Pixel Tactile theme tokens, Cubic 11 font loader, QSS, and sharp-corner Windows chrome.

Zero-overhead PySide6 styling: 0px sharp corners, solid flat surfaces, crisp 1.5-2px
ink borders, hard pixel-offset bevels, and zero blur or drop-shadow graphics effects.
"""
import os
import sys

RETRO_PIXEL = {
    # Warm Paper / Parchment surfaces
    "bg_cream": "#F5EFE2",
    "bg_sand": "#EAE2D0",
    "bg_sand_hover": "#DFD5BF",
    "bg_sand_pressed": "#D4C8AE",
    "bg_video": "#1A1715",
    "bg_console": "#1F1B18",

    # Dark Espresso Ink (text, borders, active cards)
    "ink": "#231E1A",
    "ink_active": "#26211D",
    "ink_soft": "#4A423A",
    "ink_muted": "#7C7367",
    "ink_dash": "#6E665C",

    # Terracotta Rust (Title bar, progress blocks, locked badges, hard shadow accent)
    "terracotta": "#A34E32",
    "terracotta_hover": "#B55A3C",
    "terracotta_pressed": "#8C4027",
    "terracotta_shadow": "#B96446",

    # Sage Olive Green (Play button, IP Lock ON, IP Matched badge)
    "sage": "#9BB58E",
    "sage_hover": "#A8C19B",
    "sage_pressed": "#8AA47D",

    # Window Close Hover Red
    "close_hover": "#C83E2B",
    "close_pressed": "#A83121",

    # Crisp Cream text on dark/colored surfaces
    "on_dark": "#F5EFE2",
    "on_dark_muted": "#CFC5B4",
}

# Win32 constants for sharp-corner integrated title bar (WM_NCCALCSIZE + WM_NCHITTEST)
_WM_NCCALCSIZE = 0x0083
_WM_NCHITTEST = 0x0084
_HTCAPTION = 2
_HTLEFT = 10
_HTRIGHT = 11
_HTTOP = 12
_HTTOPLEFT = 13
_HTTOPRIGHT = 14
_HTBOTTOM = 15
_HTBOTTOMLEFT = 16
_HTBOTTOMRIGHT = 17
_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_NOZORDER = 0x0004
_SWP_FRAMECHANGED = 0x0020
_SM_CXSIZEFRAME = 32
_SM_CYSIZEFRAME = 33
_SM_CXPADDEDBORDER = 92

_LOADED_FONT_FAMILY: str | None = None
_LOADED_DISPLAY_FAMILY: str | None = None


def _load_bundled_font(filename: str, fallback: str) -> str:
    from PySide6.QtGui import QFontDatabase
    import pyinstaller_utils

    candidates = [
        pyinstaller_utils.get_resource_path(os.path.join("assets", "fonts", filename)),
        pyinstaller_utils.get_resource_path(os.path.join("src", "assets", "fonts", filename)),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts", filename),
    ]
    for path in candidates:
        if os.path.exists(path):
            fid = QFontDatabase.addApplicationFont(path)
            if fid != -1:
                families = QFontDatabase.applicationFontFamilies(fid)
                if families:
                    return families[0]
    return fallback


def load_pixel_font() -> str:
    """Load bundled Cubic 11 CJK pixel font once and return its Qt family name."""
    global _LOADED_FONT_FAMILY
    if _LOADED_FONT_FAMILY is None:
        _LOADED_FONT_FAMILY = _load_bundled_font("Cubic_11.ttf", "Consolas")
    return _LOADED_FONT_FAMILY


def load_display_font() -> str:
    """Load bundled Pixelify Sans bold display font for retro English headings."""
    global _LOADED_DISPLAY_FAMILY
    if _LOADED_DISPLAY_FAMILY is None:
        _LOADED_DISPLAY_FAMILY = _load_bundled_font("PixelifySans.ttf", load_pixel_font())
    return _LOADED_DISPLAY_FAMILY


def _is_native_windows_qpa() -> bool:
    if sys.platform != "win32":
        return False
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    return app is not None and app.platformName() == "windows"


def enable_windows_integrated_chrome(window) -> bool:
    """Attach sharp-corner Windows 11 chrome (DWMWCP_DONOTROUND) + ink border.

    Preserves native Aero Snap, taskbar minimize, 8-way edge resize, and DWM shadow
    while seamlessly letting our Terracotta pixel title bar replace the OS caption.
    """
    if not _is_native_windows_qpa():
        return False
    try:
        import ctypes

        hwnd = int(window.winId())
        dwmapi = ctypes.windll.dwmapi
        user32 = ctypes.windll.user32

        # 1. Opt into dark mode titlebar fallback
        dark = ctypes.c_int(1)
        if dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark)) != 0:
            dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(dark), ctypes.sizeof(dark))

        # 2. Match DWM caption (#A34E32 -> BGR 0x00324EA3) & border (#231E1A -> BGR 0x001A1E23)
        caption_bgr = ctypes.c_uint32(0x00324EA3)
        dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption_bgr), ctypes.sizeof(caption_bgr))
        border_bgr = ctypes.c_uint32(0x001A1E23)
        dwmapi.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(border_bgr), ctypes.sizeof(border_bgr))

        # 3. Sharp retro square corners (DWMWA_WINDOW_CORNER_PREFERENCE = 33, DWMWCP_DONOTROUND = 1)
        corner = ctypes.c_int(1)
        dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corner), ctypes.sizeof(corner))

        # 4. Extend 1px frame to preserve native drop shadow without visual artifacts
        class MARGINS(ctypes.Structure):
            _fields_ = [
                ("cxLeftWidth", ctypes.c_int),
                ("cxRightWidth", ctypes.c_int),
                ("cyTopHeight", ctypes.c_int),
                ("cyBottomHeight", ctypes.c_int),
            ]

        margins = MARGINS(0, 0, 1, 0)
        dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))

        # 5. Trigger WM_NCCALCSIZE immediately
        user32.SetWindowPos(
            hwnd, 0, 0, 0, 0, 0,
            _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOZORDER | _SWP_FRAMECHANGED,
        )
        return True
    except Exception:
        return False


def handle_windows_native_event(window, title_bar, event_type, message):
    """Handle WM_NCCALCSIZE and WM_NCHITTEST for integrated sharp-corner chrome."""
    if not _is_native_windows_qpa() or event_type != b"windows_generic_MSG":
        return False, 0

    try:
        import ctypes
        from ctypes import wintypes
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QAbstractButton

        msg = wintypes.MSG.from_address(int(message))
        user32 = ctypes.windll.user32

        if msg.message == _WM_NCCALCSIZE:
            is_fs = getattr(window, "_in_fullscreen", False)
            if msg.wParam and user32.IsZoomed(msg.hWnd) and not is_fs:
                class NCCALCSIZE_PARAMS(ctypes.Structure):
                    _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]

                params = ctypes.cast(msg.lParam, ctypes.POINTER(NCCALCSIZE_PARAMS)).contents
                try:
                    dpi = user32.GetDpiForWindow(msg.hWnd) or 96
                    bx = user32.GetSystemMetricsForDpi(_SM_CXSIZEFRAME, dpi) + user32.GetSystemMetricsForDpi(_SM_CXPADDEDBORDER, dpi)
                    by = user32.GetSystemMetricsForDpi(_SM_CYSIZEFRAME, dpi) + user32.GetSystemMetricsForDpi(_SM_CXPADDEDBORDER, dpi)
                except Exception:
                    bx = user32.GetSystemMetrics(_SM_CXSIZEFRAME) + user32.GetSystemMetrics(_SM_CXPADDEDBORDER)
                    by = user32.GetSystemMetrics(_SM_CYSIZEFRAME) + user32.GetSystemMetrics(_SM_CXPADDEDBORDER)

                rect = params.rgrc[0]
                rect.left += bx
                rect.right -= bx
                rect.top += by
                rect.bottom -= by
            return True, 0

        if msg.message == _WM_NCHITTEST:
            if getattr(window, "_in_fullscreen", False):
                return False, 0

            x = ctypes.c_short(msg.lParam & 0xFFFF).value
            y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value

            win_rect = wintypes.RECT()
            user32.GetWindowRect(msg.hWnd, ctypes.byref(win_rect))

            if not user32.IsZoomed(msg.hWnd):
                try:
                    dpi = user32.GetDpiForWindow(msg.hWnd) or 96
                except Exception:
                    dpi = 96
                border = max(5, int(round(6 * dpi / 96.0)))
                left = x < win_rect.left + border
                right = x >= win_rect.right - border
                top = y < win_rect.top + border
                bottom = y >= win_rect.bottom - border

                if top and left:
                    return True, _HTTOPLEFT
                if top and right:
                    return True, _HTTOPRIGHT
                if bottom and left:
                    return True, _HTBOTTOMLEFT
                if bottom and right:
                    return True, _HTBOTTOMRIGHT
                if left:
                    return True, _HTLEFT
                if right:
                    return True, _HTRIGHT
                if top:
                    return True, _HTTOP
                if bottom:
                    return True, _HTBOTTOM

            if title_bar is not None and title_bar.isVisible():
                local_pos = title_bar.mapFromGlobal(QCursor.pos())
                if title_bar.rect().contains(local_pos):
                    child = title_bar.childAt(local_pos)
                    cur = child
                    while cur is not None and cur is not title_bar:
                        if isinstance(cur, QAbstractButton):
                            return False, 0
                        cur = cur.parentWidget()
                    return True, _HTCAPTION

    except Exception:
        return False, 0

    return False, 0


def build_player_stylesheet(
    t: dict = RETRO_PIXEL,
    font_family: str = "Cubic 11",
    display_family: str = "Pixelify Sans",
) -> str:
    """Return the Warm Retro Pixel Tactile QSS stylesheet (0px sharp corners, bold pixel type)."""
    font_stack = f'"{font_family}", "Consolas", "Microsoft JhengHei UI", monospace'
    display_stack = f'"{display_family}", "{font_family}", "Consolas", monospace'
    return f"""
    QMainWindow, QWidget {{
        font-family: {font_stack};
        font-weight: 700;
        color: {t["ink"]};
    }}
    QMainWindow {{
        background-color: {t["bg_cream"]};
    }}
    QWidget#RootContainer {{
        background-color: {t["bg_cream"]};
        border: 2px solid {t["ink"]};
    }}
    QWidget#RootContainer[fullscreen="true"] {{
        border: none;
    }}
    QWidget#StackedWidget {{
        background-color: {t["bg_cream"]};
    }}

    /* ── Terracotta Retro Title Bar ───────────────────────────────── */
    QFrame#TitleBar {{
        background-color: {t["terracotta"]};
        border-bottom: 2px solid {t["ink"]};
    }}
    QLabel#TitleAppName, QLabel#HeaderFileName {{
        font-family: {display_stack};
        color: {t["on_dark"]};
        font-size: 15px;
        font-weight: 700;
        letter-spacing: 0.8px;
    }}
    QLabel#StatusBadge {{
        color: {t["ink"]};
        background-color: {t["bg_cream"]};
        border: 1.5px solid {t["ink"]};
        border-radius: 0px;
        padding: 0px 9px;
        font-size: 13px;
        font-weight: 700;
    }}
    QLabel#StatusBadge[state="ready"] {{
        background-color: {t["sage"]};
        color: {t["ink"]};
    }}
    QLabel#StatusBadge[state="decoding"] {{
        background-color: {t["bg_cream"]};
        color: {t["ink"]};
    }}
    QLabel#StatusBadge[state="warning"] {{
        background-color: {t["bg_sand"]};
        color: {t["terracotta"]};
    }}
    QPushButton#HeaderOpenBtn {{
        background-color: {t["bg_cream"]};
        color: {t["ink"]};
        border: 1.5px solid {t["ink"]};
        border-right: 2.5px solid {t["ink"]};
        border-bottom: 2.5px solid {t["ink"]};
        border-radius: 0px;
        padding: 0px 10px;
        font-size: 13px;
        font-weight: 700;
    }}
    QPushButton#HeaderOpenBtn:hover {{
        background-color: {t["bg_sand"]};
    }}
    QPushButton#HeaderOpenBtn:pressed {{
        background-color: {t["bg_sand_pressed"]};
        border-right: 1.5px solid {t["ink"]};
        border-bottom: 1.5px solid {t["ink"]};
    }}

    /* Retro Square Cream Caption Buttons inside Terracotta Bar */
    QPushButton#WinMinBtn, QPushButton#WinMaxBtn, QPushButton#WinCloseBtn {{
        background-color: {t["bg_cream"]};
        border: 1.5px solid {t["ink"]};
        border-radius: 0px;
        min-width: 26px;
        max-width: 26px;
        min-height: 26px;
        max-height: 26px;
        padding: 0px;
    }}
    QPushButton#WinMinBtn:hover, QPushButton#WinMaxBtn:hover {{
        background-color: {t["bg_sand"]};
    }}
    QPushButton#WinMinBtn:pressed, QPushButton#WinMaxBtn:pressed {{
        background-color: {t["bg_sand_pressed"]};
    }}
    QPushButton#WinCloseBtn:hover {{
        background-color: {t["close_hover"]};
    }}
    QPushButton#WinCloseBtn:pressed {{
        background-color: {t["close_pressed"]};
    }}

    /* ── Landing Page (Hero Typography + Double-Framed Sage Drop Zone) */
    QFrame#LandingPage {{
        background-color: {t["bg_cream"]};
    }}
    QLabel#WelcomeTitle {{
        font-family: {display_stack};
        color: {t["ink"]};
        font-size: 38px;
        font-weight: 700;
        letter-spacing: 0.5px;
    }}
    QLabel#WelcomeSub {{
        color: {t["ink"]};
        font-size: 19px;
        font-weight: 700;
    }}
    QFrame#CursorBlock {{
        background-color: {t["terracotta"]};
        border: none;
        min-width: 14px;
        max-width: 14px;
        min-height: 20px;
        max-height: 20px;
    }}

    /* ── Video Stage ──────────────────────────────────────────────── */
    QFrame#PlayerPage {{
        background-color: {t["bg_cream"]};
    }}
    QFrame#VideoContainerFrame {{
        background-color: {t["bg_video"]};
        border: none;
    }}

    /* ── Docked Retro Decoding / Buffer Strip ─────────────────────── */
    QFrame#BufferStrip {{
        background-color: {t["bg_sand"]};
        border-top: 2px solid {t["ink"]};
    }}
    QLabel#BufferStripTitle {{
        color: {t["ink"]};
        font-size: 14px;
    }}
    QLabel#BufferStripDetail {{
        color: {t["ink_soft"]};
        font-size: 13px;
    }}
    QProgressBar#BufferProgressBar {{
        background-color: {t["bg_cream"]};
        border: 1.5px solid {t["ink"]};
        border-radius: 0px;
        padding: 2px;
    }}
    QProgressBar#BufferProgressBar::chunk {{
        background-color: {t["terracotta"]};
        width: 8px;
        margin: 0px 1px;
    }}

    /* ── Single-Row Hardware Bottom Control Bar ───────────────────── */
    QFrame#ControlBarFrame {{
        background-color: {t["bg_cream"]};
        border-top: 2px solid {t["ink"]};
    }}
    QPushButton#PlayButton {{
        background-color: {t["sage"]};
        color: {t["ink"]};
        border: 1.5px solid {t["ink"]};
        border-right: 3px solid {t["ink"]};
        border-bottom: 3px solid {t["ink"]};
        border-radius: 0px;
        min-width: 36px;
        max-width: 36px;
        min-height: 36px;
        max-height: 36px;
    }}
    QPushButton#PlayButton:hover {{
        background-color: {t["sage_hover"]};
    }}
    QPushButton#PlayButton:pressed {{
        background-color: {t["sage_pressed"]};
        border-right: 1.5px solid {t["ink"]};
        border-bottom: 1.5px solid {t["ink"]};
    }}
    QLabel#TimeLabel {{
        color: {t["ink"]};
        font-size: 14px;
        padding: 0px 4px;
    }}
    QPushButton#MuteButton, QPushButton#StatsButton,
    QPushButton#TracksToggleButton, QPushButton#FullscreenButton {{
        background-color: {t["bg_cream"]};
        color: {t["ink"]};
        border: 1.5px solid {t["ink"]};
        border-radius: 0px;
        min-width: 32px;
        max-width: 32px;
        min-height: 32px;
        max-height: 32px;
        padding: 0px;
    }}
    QPushButton#MuteButton:hover, QPushButton#StatsButton:hover,
    QPushButton#TracksToggleButton:hover, QPushButton#FullscreenButton:hover {{
        background-color: {t["bg_sand"]};
    }}
    QPushButton#MuteButton:pressed, QPushButton#StatsButton:pressed,
    QPushButton#TracksToggleButton:pressed, QPushButton#FullscreenButton:pressed {{
        background-color: {t["bg_sand_pressed"]};
    }}
    QPushButton#TracksToggleButton[active="true"],
    QPushButton#StatsButton[active="true"] {{
        background-color: {t["ink"]};
        color: {t["on_dark"]};
    }}
    QFrame#ControlDivider {{
        background-color: {t["ink"]};
        min-width: 2px;
        max-width: 2px;
        min-height: 26px;
        max-height: 26px;
    }}

    /* ── Right Warm Cream Collapsible Sidebar ─────────────────────── */
    QFrame#SidebarFrame {{
        background-color: {t["bg_cream"]};
        border-left: 2px solid {t["ink"]};
    }}
    QLabel#SidebarTitle {{
        color: {t["ink"]};
        font-size: 18px;
    }}
    QPushButton#DrawerCollapseBtn, QPushButton#DrawerBackBtn {{
        background-color: {t["bg_sand"]};
        color: {t["ink"]};
        border: 1.5px solid {t["ink"]};
        border-radius: 0px;
        min-width: 28px;
        max-width: 28px;
        min-height: 28px;
        max-height: 28px;
        padding: 0px;
    }}
    QPushButton#DrawerCollapseBtn:hover, QPushButton#DrawerBackBtn:hover {{
        background-color: {t["bg_sand_hover"]};
    }}
    QPushButton#DrawerCollapseBtn:pressed, QPushButton#DrawerBackBtn:pressed {{
        background-color: {t["bg_sand_pressed"]};
    }}
    QFrame#IpLockBox {{
        background-color: {t["bg_sand"]};
        border: 1.5px solid {t["ink"]};
        border-radius: 0px;
    }}
    QLabel#IpLockTitle {{
        color: {t["ink"]};
        font-size: 14px;
    }}
    QLabel#TrackCountCaption {{
        font-family: {display_stack};
        color: {t["ink_muted"]};
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.8px;
    }}
    QListWidget#LanguageList {{
        background-color: transparent;
        border: none;
        outline: none;
    }}
    QPushButton#DetailsBottomBtn {{
        background-color: {t["bg_sand"]};
        color: {t["ink"]};
        border: 1.5px solid {t["ink"]};
        border-right: 3px solid {t["ink"]};
        border-bottom: 3px solid {t["ink"]};
        border-radius: 0px;
        padding: 9px 12px;
        font-size: 14px;
    }}
    QPushButton#DetailsBottomBtn:hover {{
        background-color: {t["bg_sand_hover"]};
    }}
    QPushButton#DetailsBottomBtn:pressed {{
        background-color: {t["bg_sand_pressed"]};
        border-right: 1.5px solid {t["ink"]};
        border-bottom: 1.5px solid {t["ink"]};
    }}

    /* ── Details Sub-View inside Sidebar ──────────────────────────── */
    QFrame#SegmentBar {{
        background-color: {t["bg_sand"]};
        border: 1.5px solid {t["ink"]};
        border-radius: 0px;
    }}
    QPushButton#TabInfoBtn, QPushButton#TabLogBtn {{
        background-color: transparent;
        color: {t["ink_soft"]};
        border: none;
        border-radius: 0px;
        padding: 6px 8px;
        font-size: 13px;
    }}
    QPushButton#TabInfoBtn:hover, QPushButton#TabLogBtn:hover {{
        color: {t["ink"]};
        background-color: {t["bg_sand_hover"]};
    }}
    QPushButton#TabInfoBtn[active="true"], QPushButton#TabLogBtn[active="true"] {{
        background-color: {t["ink"]};
        color: {t["on_dark"]};
    }}
    QFrame#SecurityInfoFrame {{
        background-color: {t["bg_sand"]};
        border: 1.5px solid {t["ink"]};
        border-radius: 0px;
    }}
    QLabel#SectionCaption {{
        color: {t["terracotta"]};
        font-size: 12px;
        letter-spacing: 0.5px;
    }}
    QLabel#InfoKey {{
        color: {t["ink_muted"]};
        font-size: 12px;
    }}
    QLabel#InfoVal {{
        color: {t["ink"]};
        font-size: 13px;
    }}
    QPushButton#WebSimButton {{
        background-color: {t["terracotta"]};
        color: {t["on_dark"]};
        border: 1.5px solid {t["ink"]};
        border-right: 3px solid {t["ink"]};
        border-bottom: 3px solid {t["ink"]};
        border-radius: 0px;
        padding: 8px 12px;
        font-size: 13px;
    }}
    QPushButton#WebSimButton:hover {{
        background-color: {t["terracotta_hover"]};
    }}
    QPlainTextEdit#TerminalConsole {{
        background-color: {t["bg_console"]};
        color: {t["on_dark"]};
        border: 1.5px solid {t["ink"]};
        border-radius: 0px;
        padding: 8px;
        font-size: 12px;
    }}

    /* ── Crisp Retro Square Scrollbars ────────────────────────────── */
    QScrollBar:vertical {{
        background: {t["bg_sand"]};
        width: 10px;
        border-left: 1px solid {t["ink"]};
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background-color: {t["ink"]};
        min-height: 28px;
        margin: 2px;
        border-radius: 0px;
    }}
    QScrollBar::handle:vertical:hover {{
        background-color: {t["terracotta"]};
    }}
    QScrollBar::sub-line:vertical, QScrollBar::add-line:vertical,
    QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical,
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        height: 0px;
        background: none;
        border: none;
    }}
    QScrollBar:horizontal {{
        background: {t["bg_sand"]};
        height: 10px;
        border-top: 1px solid {t["ink"]};
        margin: 0px;
    }}
    QScrollBar::handle:horizontal {{
        background-color: {t["ink"]};
        min-width: 28px;
        margin: 2px;
        border-radius: 0px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background-color: {t["terracotta"]};
    }}
    QScrollBar::sub-line:horizontal, QScrollBar::add-line:horizontal,
    QScrollBar::left-arrow:horizontal, QScrollBar::right-arrow:horizontal,
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        width: 0px;
        background: none;
        border: none;
    }}

    /* ── MessageBox Retro Styling ─────────────────────────────────── */
    QMessageBox {{
        background-color: {t["bg_cream"]};
        color: {t["ink"]};
    }}
    QMessageBox QLabel {{
        color: {t["ink"]};
        font-size: 13px;
    }}
    QMessageBox QPushButton {{
        background-color: {t["bg_sand"]};
        color: {t["ink"]};
        border: 1.5px solid {t["ink"]};
        padding: 5px 16px;
        min-width: 72px;
    }}
    QMessageBox QPushButton:hover {{
        background-color: {t["sage"]};
    }}
    """
