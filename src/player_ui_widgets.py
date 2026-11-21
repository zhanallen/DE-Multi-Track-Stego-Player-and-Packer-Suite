"""Warm Retro Pixel Tactile custom widgets for StegoPlayer.

All widgets use direct, zero-overhead QPainter primitives (0px sharp corners,
segmented progress blocks, mechanical toggle switch, and a zero-widget-bloat
custom QStyledItemDelegate for track cards).
"""
from PySide6.QtCore import Qt, Signal, QRect, QRectF, QSize, QPointF
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QAbstractButton, QStyle, QStyledItemDelegate, QWidget
)
from PySide6.QtMultimediaWidgets import QVideoWidget

from player_ui_theme import RETRO_PIXEL

# Custom item data roles for RetroTrackDelegate (Qt.UserRole remains lang_code)
ROLE_DISPLAY_NAME = Qt.ItemDataRole.UserRole + 1
ROLE_BADGE_TEXT = Qt.ItemDataRole.UserRole + 2
ROLE_TRACK_STATE = Qt.ItemDataRole.UserRole + 3  # "matched" | "allowed" | "locked" | "free"


class RetroSegmentedSlider(QWidget):
    """Segmented terracotta-block progress bar with bold square playhead thumb.

    Supports instant click-to-seek and zero-spam drag preview (`previewChanged`
    fires while dragging; `seekRequested` fires once on click or release).
    """

    dragStarted = Signal()
    previewChanged = Signal(int)
    seekRequested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._min = 0
        self._max = 0
        self._val = 0
        self._dragging = False
        self.setFixedHeight(28)
        self.setMinimumWidth(140)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def minimum(self) -> int:
        return self._min

    def maximum(self) -> int:
        return self._max

    def value(self) -> int:
        return self._val

    def setRange(self, lo: int, hi: int) -> None:
        self._min = int(lo)
        self._max = max(int(lo), int(hi))
        self._val = max(self._min, min(self._max, self._val))
        self.update()

    def setValue(self, val: int) -> None:
        clamped = max(self._min, min(self._max, int(val)))
        if clamped != self._val:
            self._val = clamped
            self.update()

    def _x_to_value(self, x: float) -> int:
        if self._max <= self._min:
            return self._min
        pad = 5.0
        usable = max(1.0, self.width() - pad * 2)
        ratio = max(0.0, min(1.0, (x - pad) / usable))
        return int(round(self._min + ratio * (self._max - self._min)))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._max > self._min:
            self._dragging = True
            self.dragStarted.emit()
            val = self._x_to_value(event.position().x())
            self.setValue(val)
            self.previewChanged.emit(val)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging and self._max > self._min:
            val = self._x_to_value(event.position().x())
            if val != self._val:
                self.setValue(val)
                self.previewChanged.emit(val)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            val = self._x_to_value(event.position().x())
            self.setValue(val)
            self.seekRequested.emit(val)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        w = self.width()
        h = self.height()
        pad = 5
        track_h = 14
        track_y = (h - track_h) // 2
        track_w = max(8, w - pad * 2)

        # 1. Outer cream/sand track with crisp dark ink border
        track_rect = QRect(pad, track_y, track_w, track_h)
        p.fillRect(track_rect, QColor(RETRO_PIXEL["bg_sand"]))
        p.setPen(QPen(QColor(RETRO_PIXEL["ink"]), 2))
        p.drawRect(track_rect.adjusted(0, 0, -1, -1))

        # 2. Ratio & playhead x
        ratio = (self._val - self._min) / (self._max - self._min) if self._max > self._min else 0.0
        ratio = max(0.0, min(1.0, ratio))
        fill_x = pad + int(round(ratio * track_w))

        # 3. Terracotta segmented blocks up to playhead
        inner_left = pad + 4
        inner_top = track_y + 3
        inner_h = track_h - 6
        block_w = 6
        gap = 2
        step = block_w + gap
        block_col = QColor(RETRO_PIXEL["terracotta"])
        limit_x = min(fill_x - 3, pad + track_w - 4)
        bx = inner_left
        while bx + block_w <= limit_x:
            p.fillRect(bx, inner_top, block_w, inner_h, block_col)
            bx += step
        # Partial trailing sliver if there is room >= 3px before thumb
        rem = limit_x - bx
        if rem >= 3:
            p.fillRect(bx, inner_top, rem, inner_h, block_col)

        # 4. Bold vertical dark rectangular thumb
        thumb_w = 8
        thumb_h = 22
        thumb_x = max(pad - 2, min(w - pad - thumb_w + 2, fill_x - thumb_w // 2))
        thumb_y = (h - thumb_h) // 2
        p.fillRect(thumb_x, thumb_y, thumb_w, thumb_h, QColor(RETRO_PIXEL["ink"]))
        p.end()


class RetroVolumeBar(QWidget):
    """Crisp bordered horizontal retro volume bar (click & drag)."""

    seekRequested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._min = 0
        self._max = 100
        self._val = 80
        self._dragging = False
        self.setFixedSize(82, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def value(self) -> int:
        return self._val

    def setRange(self, lo: int, hi: int) -> None:
        self._min = int(lo)
        self._max = max(int(lo), int(hi))
        self.update()

    def setValue(self, val: int) -> None:
        clamped = max(self._min, min(self._max, int(val)))
        if clamped != self._val:
            self._val = clamped
            self.update()

    def _x_to_val(self, x: float) -> int:
        usable = max(1.0, self.width() - 4.0)
        ratio = max(0.0, min(1.0, (x - 2.0) / usable))
        return int(round(self._min + ratio * (self._max - self._min)))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            val = self._x_to_val(event.position().x())
            self.setValue(val)
            self.seekRequested.emit(val)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            val = self._x_to_val(event.position().x())
            if val != self._val:
                self.setValue(val)
                self.seekRequested.emit(val)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        bar_h = 10
        bar_y = (self.height() - bar_h) // 2
        bar_rect = QRect(0, bar_y, self.width(), bar_h)

        p.fillRect(bar_rect, QColor(RETRO_PIXEL["bg_sand"]))
        p.setPen(QPen(QColor(RETRO_PIXEL["ink"]), 2))
        p.drawRect(bar_rect.adjusted(0, 0, -1, -1))

        ratio = (self._val - self._min) / max(1, (self._max - self._min))
        inner_w = max(0, int(round((self.width() - 6) * ratio)))
        if inner_w > 0:
            p.fillRect(3, bar_y + 3, inner_w, bar_h - 6, QColor(RETRO_PIXEL["ink"]))
        p.end()


class RetroToggleSwitch(QAbstractButton):
    """Mechanical rectangular toggle switch (Sage green ON / sand OFF + dark square thumb)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(46, 22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        r = self.rect()
        bg = QColor(RETRO_PIXEL["sage"] if self.isChecked() else RETRO_PIXEL["bg_cream"])
        p.fillRect(r, bg)
        p.setPen(QPen(QColor(RETRO_PIXEL["ink"]), 2))
        p.drawRect(r.adjusted(0, 0, -1, -1))

        thumb_size = 14
        thumb_y = (r.height() - thumb_size) // 2
        thumb_x = r.width() - thumb_size - 4 if self.isChecked() else 4
        p.fillRect(thumb_x, thumb_y, thumb_size, thumb_size, QColor(RETRO_PIXEL["ink"]))
        p.end()


class RetroTrackDelegate(QStyledItemDelegate):
    """High-performance custom renderer for the 3 retro audio track card states.

    States:
    - Selected/Active: dark espresso fill, cream text, left triangle, sage badge,
      and 2px terracotta offset drop shadow.
    - Allowed/Free: warm cream fill, solid ink border, crisp outlined badge.
    - Locked: recessed warm sand fill, dashed border, muted text, terracotta lock badge.
    """

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), 52)

    def paint(self, painter: QPainter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        display_name = index.data(ROLE_DISPLAY_NAME) or index.data(Qt.ItemDataRole.DisplayRole) or ""
        badge_text = index.data(ROLE_BADGE_TEXT) or ""
        state = index.data(ROLE_TRACK_STATE) or "free"
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        # Card rect with clean vertical gap and 2px right/bottom room for hard shadow
        card = option.rect.adjusted(0, 3, -3, -5)

        if is_selected:
            # Hard 2px terracotta offset shadow (matching reference active card)
            shadow = card.translated(2, 2)
            painter.fillRect(shadow, QColor(RETRO_PIXEL["terracotta_shadow"]))
            painter.fillRect(card, QColor(RETRO_PIXEL["ink_active"]))
            painter.setPen(QPen(QColor(RETRO_PIXEL["ink"]), 2))
            painter.drawRect(card.adjusted(0, 0, -1, -1))
            text_color = QColor(RETRO_PIXEL["on_dark"])
        elif state == "locked":
            bg = QColor(RETRO_PIXEL["bg_sand_hover"] if is_hovered else RETRO_PIXEL["bg_sand"])
            painter.fillRect(card, bg)
            dash_pen = QPen(QColor(RETRO_PIXEL["ink_dash"]), 1.5, Qt.PenStyle.DashLine)
            painter.setPen(dash_pen)
            painter.drawRect(card.adjusted(0, 0, -1, -1))
            text_color = QColor(RETRO_PIXEL["ink_muted"])
        else:
            bg = QColor(RETRO_PIXEL["bg_sand"] if is_hovered else RETRO_PIXEL["bg_cream"])
            painter.fillRect(card, bg)
            painter.setPen(QPen(QColor(RETRO_PIXEL["ink"]), 1.5))
            painter.drawRect(card.adjusted(0, 0, -1, -1))
            text_color = QColor(RETRO_PIXEL["ink"])

        # Right-side status badge measurement
        badge_font = QFont(option.font)
        badge_font.setPixelSize(12)
        badge_font.setBold(True)
        bfm = QFontMetrics(badge_font)
        badge_rect = QRect()

        if badge_text:
            lock_extra = 13 if state == "locked" else 0
            bw = bfm.horizontalAdvance(badge_text) + 14 + lock_extra
            bh = 22
            bx = card.right() - bw - 9
            by = card.top() + (card.height() - bh) // 2
            badge_rect = QRect(bx, by, bw, bh)

            if is_selected or state == "matched":
                painter.fillRect(badge_rect, QColor(RETRO_PIXEL["sage"]))
                badge_fg = QColor(RETRO_PIXEL["ink"])
            elif state == "locked":
                painter.fillRect(badge_rect, QColor(RETRO_PIXEL["terracotta"]))
                badge_fg = QColor(RETRO_PIXEL["on_dark"])
            else:
                painter.fillRect(badge_rect, QColor(RETRO_PIXEL["bg_cream"]))
                painter.setPen(QPen(QColor(RETRO_PIXEL["ink"]), 1.2))
                painter.drawRect(badge_rect.adjusted(0, 0, -1, -1))
                badge_fg = QColor(RETRO_PIXEL["ink"])

            # Optional crisp mini lock icon inside terracotta locked badge
            text_x_offset = 0
            if state == "locked":
                lx = badge_rect.left() + 6
                ly = badge_rect.top() + 5
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                painter.setPen(QPen(badge_fg, 1.3))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawArc(QRectF(lx + 1.5, ly, 5.0, 5.5), 0, 180 * 16)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(badge_fg)
                painter.drawRect(QRectF(lx, ly + 4.5, 8.0, 6.5))
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
                text_x_offset = 10

            painter.setFont(badge_font)
            painter.setPen(badge_fg)
            badge_text_rect = badge_rect.adjusted(text_x_offset, 0, 0, 0)
            painter.drawText(badge_text_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

        # Left active triangle indicator + track name
        left_x = card.left() + 12
        if is_selected:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(RETRO_PIXEL["on_dark"]))
            cy = card.top() + card.height() / 2.0
            tri = QPolygonF([
                QPointF(left_x, cy - 4.0),
                QPointF(left_x + 5.5, cy),
                QPointF(left_x, cy + 4.0),
            ])
            painter.drawPolygon(tri)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            left_x += 13

        name_font = QFont(option.font)
        name_font.setPixelSize(15)
        name_font.setBold(True)
        painter.setFont(name_font)
        painter.setPen(text_color)

        right_bound = (badge_rect.left() - 8) if badge_text else (card.right() - 10)
        name_rect = QRect(left_x, card.top(), max(20, right_bound - left_x), card.height())
        elided = QFontMetrics(name_font).elidedText(display_name, Qt.TextElideMode.ElideRight, name_rect.width())
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided)

        painter.restore()


class RetroDropHeroWidget(QWidget):
    """Double-framed Sage Green retro drop zone matching the uploaded landing artwork.

    Clicking anywhere inside opens the file dialog; dragging a video file over the
    window switches the prompt to '放開以載入影片' and previews the dragged filename.
    """

    clicked = Signal()

    def __init__(self, pixel_font: str = "Cubic 11", display_font: str = "Pixelify Sans", parent=None):
        super().__init__(parent)
        self._pixel_font = pixel_font
        self._display_font = display_font
        self._hovered = False
        self._drag_active = False
        self._badge_filename = "demo.mp4"
        self.setMinimumSize(620, 290)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_drag_state(self, active: bool, filename: str | None = None) -> None:
        new_name = filename if (active and filename) else "demo.mp4"
        if self._drag_active != active or self._badge_filename != new_name:
            self._drag_active = active
            self._badge_filename = new_name
            self.update()

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        ink = QColor(RETRO_PIXEL["ink"])
        cream = QColor(RETRO_PIXEL["bg_cream"])
        terra = QColor(RETRO_PIXEL["terracotta"])

        # 1. Outer 2px dark frame + 7px cream gutter + inner 2px dark frame
        outer = self.rect().adjusted(1, 1, -2, -2)
        p.fillRect(outer, cream)
        p.setPen(QPen(ink, 2))
        p.drawRect(outer)

        inner = outer.adjusted(8, 8, -8, -8)
        if self._drag_active:
            sage_fill = QColor("#93AF85")
        elif self._hovered:
            sage_fill = QColor("#B0C6A4")
        else:
            sage_fill = QColor("#A4BC98")
        p.fillRect(inner, sage_fill)
        p.setPen(QPen(ink, 2))
        p.drawRect(inner)

        cx = inner.center().x()
        cy = inner.center().y()

        # 2. Pixel-art Download Arrow (dark ink) + Terracotta U-Tray
        px = 6  # 6px crisp pixel grid unit
        icon_top = inner.top() + max(28, int(inner.height() * 0.16))

        # Arrow shaft (2 cols x 4 rows) + stepped arrowhead
        arrow_blocks = [
            (-1, 0), (0, 0),
            (-1, 1), (0, 1),
            (-1, 2), (0, 2),
            (-3, 3), (-2, 3), (-1, 3), (0, 3), (1, 3), (2, 3),
            (-2, 4), (-1, 4), (0, 4), (1, 4),
            (-1, 5), (0, 5),
        ]
        for gx, gy in arrow_blocks:
            p.fillRect(cx + gx * px, icon_top + gy * px, px, px, ink)

        # Terracotta tray below arrow (with crisp 2px vertical gap)
        tray_y = icon_top + 7 * px + 2
        tray_blocks = [
            (-4, 0), (3, 0),
            (-4, 1), (3, 1),
            (-4, 2), (-3, 2), (-2, 2), (-1, 2), (0, 2), (1, 2), (2, 2), (3, 2),
        ]
        for gx, gy in tray_blocks:
            p.fillRect(cx + gx * px, tray_y + gy * px, px, px, terra)

        # 3. Bold Main Prompt Text
        main_y = tray_y + 3 * px + 20
        title_font = QFont(self._pixel_font)
        title_font.setPixelSize(27)
        title_font.setBold(True)
        p.setFont(title_font)
        p.setPen(ink)
        prompt_text = "放開以載入影片" if self._drag_active else "點擊或拖曳以載入影片"
        p.drawText(QRect(inner.left() + 16, main_y, inner.width() - 32, 38), Qt.AlignmentFlag.AlignCenter, prompt_text)

        # 4. Bold Pixelify Sans Sub-caption: READY TO DECODE ▼
        sub_y = main_y + 42
        sub_font = QFont(self._display_font)
        sub_font.setPixelSize(14)
        sub_font.setBold(True)
        sub_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)
        p.setFont(sub_font)
        p.setPen(ink)
        p.drawText(QRect(inner.left() + 16, sub_y, inner.width() - 32, 24), Qt.AlignmentFlag.AlignCenter, "READY TO DECODE ▼")

        # 5. Decorative Tilted Cream File Chip ([🎞 demo.mp4]) + Pixel Cursor (bottom-right)
        p.save()
        chip_w, chip_h = 166, 42
        chip_cx = min(inner.right() - chip_w // 2 - 28, cx + 272)
        chip_cy = min(inner.bottom() - chip_h // 2 - 24, sub_y + 18)
        p.translate(chip_cx, chip_cy)
        p.rotate(-4.5)

        chip_rect = QRect(-chip_w // 2, -chip_h // 2, chip_w, chip_h)
        # Hard dark drop shadow under tilted card
        p.fillRect(chip_rect.translated(3, 4), ink)
        p.fillRect(chip_rect, cream)
        p.setPen(QPen(ink, 2))
        p.drawRect(chip_rect)

        # Mini dark pixel film icon inside left of chip
        fx = chip_rect.left() + 14
        fy = chip_rect.top() + (chip_h - 14) // 2
        p.fillRect(fx, fy, 18, 14, ink)
        # Sprocket & center screen cutouts in cream
        p.fillRect(fx + 2, fy + 2, 2, 2, cream)
        p.fillRect(fx + 2, fy + 6, 2, 2, cream)
        p.fillRect(fx + 2, fy + 10, 2, 2, cream)
        p.fillRect(fx + 14, fy + 2, 2, 2, cream)
        p.fillRect(fx + 14, fy + 6, 2, 2, cream)
        p.fillRect(fx + 14, fy + 10, 2, 2, cream)
        p.fillRect(fx + 6, fy + 4, 6, 6, cream)

        # Filename inside chip
        chip_font = QFont(self._pixel_font)
        chip_font.setPixelSize(14)
        chip_font.setBold(True)
        p.setFont(chip_font)
        p.setPen(ink)
        label_rect = QRect(fx + 26, chip_rect.top(), chip_w - 44, chip_h)
        elided = QFontMetrics(chip_font).elidedText(self._badge_filename, Qt.TextElideMode.ElideMiddle, label_rect.width())
        p.drawText(label_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided)
        p.restore()

        # Cute crisp pixel arrow cursor at bottom-right edge of the tilted chip
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        cur_x = chip_cx + chip_w // 2 - 4
        cur_y = chip_cy + chip_h // 2 - 12
        cursor_poly = QPolygonF([
            QPointF(cur_x, cur_y),
            QPointF(cur_x, cur_y + 18),
            QPointF(cur_x + 4.5, cur_y + 14.5),
            QPointF(cur_x + 7.5, cur_y + 20),
            QPointF(cur_x + 10.5, cur_y + 18.5),
            QPointF(cur_x + 7.5, cur_y + 13),
            QPointF(cur_x + 12.5, cur_y + 12.5),
        ])
        p.setBrush(cream)
        p.setPen(QPen(ink, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap, Qt.PenJoinStyle.MiterJoin))
        p.drawPolygon(cursor_poly)
        p.restore()

        p.end()


class VideoStageWidget(QVideoWidget):
    """Native hardware-backed video surface with double-click fullscreen support."""

    doubleClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.doubleClicked.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
