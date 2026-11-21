"""Crisp geometric retro pixel-aligned icons rendered via QPainter and cached as QIcon.

Zero external asset files and zero QtSvg runtime dependency.
"""
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

_ICON_CACHE: dict[tuple[str, int, str], QIcon] = {}


def get_icon(name: str, size: int = 16, color: str = "#231E1A") -> QIcon:
    """Return a cached HiDPI QIcon drawn cleanly on a 24x24 virtual pixel grid."""
    key = (name, size, color)
    cached = _ICON_CACHE.get(key)
    if cached is not None:
        return cached

    dpr = 2
    px = QPixmap(size * dpr, size * dpr)
    px.setDevicePixelRatio(dpr)
    px.fill(Qt.GlobalColor.transparent)

    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    scale = size / 24.0
    p.scale(scale, scale)

    col = QColor(color)
    pen = QPen(col, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap, Qt.PenJoinStyle.MiterJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    if name == "play":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        poly = QPolygonF([QPointF(7.5, 4.5), QPointF(19.5, 12.0), QPointF(7.5, 19.5)])
        p.drawPolygon(poly)

    elif name == "pause":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawRect(QRectF(6.0, 5.0, 4.2, 14.0))
        p.drawRect(QRectF(13.8, 5.0, 4.2, 14.0))

    elif name == "volume_high":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        poly = QPolygonF([
            QPointF(3.5, 9.0), QPointF(7.8, 9.0), QPointF(13.0, 4.8),
            QPointF(13.0, 19.2), QPointF(7.8, 15.0), QPointF(3.5, 15.0),
        ])
        p.drawPolygon(poly)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(col, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap))
        p.drawArc(QRectF(13.0, 8.2, 4.8, 7.6), -48 * 16, 96 * 16)
        p.drawArc(QRectF(14.6, 5.4, 6.8, 13.2), -50 * 16, 100 * 16)

    elif name == "volume_low":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        poly = QPolygonF([
            QPointF(3.5, 9.0), QPointF(7.8, 9.0), QPointF(13.0, 4.8),
            QPointF(13.0, 19.2), QPointF(7.8, 15.0), QPointF(3.5, 15.0),
        ])
        p.drawPolygon(poly)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(col, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap))
        p.drawArc(QRectF(13.0, 8.2, 4.8, 7.6), -48 * 16, 96 * 16)

    elif name == "volume_mute":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        poly = QPolygonF([
            QPointF(3.0, 9.0), QPointF(7.2, 9.0), QPointF(12.2, 4.8),
            QPointF(12.2, 19.2), QPointF(7.2, 15.0), QPointF(3.0, 15.0),
        ])
        p.drawPolygon(poly)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(col, 2.1, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap))
        p.drawLine(QPointF(15.5, 9.0), QPointF(20.8, 15.0))
        p.drawLine(QPointF(20.8, 9.0), QPointF(15.5, 15.0))

    elif name == "globe":
        p.drawEllipse(QRectF(3.5, 3.5, 17.0, 17.0))
        p.drawLine(QPointF(3.8, 12.0), QPointF(20.2, 12.0))
        p.drawLine(QPointF(12.0, 3.8), QPointF(12.0, 20.2))
        p.drawEllipse(QRectF(7.5, 3.5, 9.0, 17.0))

    elif name == "stats_bars":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawRect(QRectF(4.0, 12.5, 3.8, 7.5))
        p.drawRect(QRectF(10.1, 5.5, 3.8, 14.5))
        p.drawRect(QRectF(16.2, 9.5, 3.8, 10.5))

    elif name == "lock":
        p.drawArc(QRectF(7.5, 4.0, 9.0, 9.0), 0, 180 * 16)
        p.drawLine(QPointF(7.5, 8.5), QPointF(7.5, 10.5))
        p.drawLine(QPointF(16.5, 8.5), QPointF(16.5, 10.5))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawRect(QRectF(5.5, 10.5, 13.0, 10.0))

    elif name == "unlock":
        p.drawArc(QRectF(7.5, 4.0, 9.0, 9.0), 0, 150 * 16)
        p.drawLine(QPointF(7.5, 8.5), QPointF(7.5, 10.5))
        p.drawRect(QRectF(5.5, 10.5, 13.0, 9.5))

    elif name == "collapse_right":
        # Crisp double chevron >>
        p.drawPolyline(QPolygonF([QPointF(6.5, 6.5), QPointF(11.5, 12.0), QPointF(6.5, 17.5)]))
        p.drawPolyline(QPolygonF([QPointF(12.8, 6.5), QPointF(17.8, 12.0), QPointF(12.8, 17.5)]))

    elif name == "back_left":
        # Crisp double chevron <<
        p.drawPolyline(QPolygonF([QPointF(17.5, 6.5), QPointF(12.5, 12.0), QPointF(17.5, 17.5)]))
        p.drawPolyline(QPolygonF([QPointF(11.2, 6.5), QPointF(6.2, 12.0), QPointF(11.2, 17.5)]))

    elif name == "info":
        p.drawRect(QRectF(4.0, 4.0, 16.0, 16.0))
        p.drawLine(QPointF(12.0, 11.2), QPointF(12.0, 16.2))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawRect(QRectF(10.8, 7.2, 2.4, 2.4))

    elif name == "folder_open":
        path = QPainterPath()
        path.moveTo(3.2, 6.5)
        path.lineTo(9.5, 6.5)
        path.lineTo(11.5, 9.0)
        path.lineTo(20.8, 9.0)
        path.lineTo(20.8, 18.5)
        path.lineTo(3.2, 18.5)
        path.closeSubpath()
        p.drawPath(path)

    elif name == "fullscreen":
        p.drawPolyline(QPolygonF([QPointF(4.0, 9.2), QPointF(4.0, 4.0), QPointF(9.2, 4.0)]))
        p.drawPolyline(QPolygonF([QPointF(14.8, 4.0), QPointF(20.0, 4.0), QPointF(20.0, 9.2)]))
        p.drawPolyline(QPolygonF([QPointF(20.0, 14.8), QPointF(20.0, 20.0), QPointF(14.8, 20.0)]))
        p.drawPolyline(QPolygonF([QPointF(9.2, 20.0), QPointF(4.0, 20.0), QPointF(4.0, 14.8)]))

    elif name == "fullscreen_exit":
        p.drawPolyline(QPolygonF([QPointF(4.0, 9.2), QPointF(9.2, 9.2), QPointF(9.2, 4.0)]))
        p.drawPolyline(QPolygonF([QPointF(14.8, 4.0), QPointF(14.8, 9.2), QPointF(20.0, 9.2)]))
        p.drawPolyline(QPolygonF([QPointF(20.0, 14.8), QPointF(14.8, 14.8), QPointF(14.8, 20.0)]))
        p.drawPolyline(QPolygonF([QPointF(9.2, 20.0), QPointF(9.2, 14.8), QPointF(4.0, 14.8)]))

    elif name == "film":
        p.drawRect(QRectF(3.0, 4.5, 18.0, 15.0))
        p.drawLine(QPointF(7.5, 4.5), QPointF(7.5, 19.5))
        p.drawLine(QPointF(16.5, 4.5), QPointF(16.5, 19.5))
        p.drawLine(QPointF(3.0, 9.5), QPointF(7.5, 9.5))
        p.drawLine(QPointF(3.0, 14.5), QPointF(7.5, 14.5))
        p.drawLine(QPointF(16.5, 9.5), QPointF(21.0, 9.5))
        p.drawLine(QPointF(16.5, 14.5), QPointF(21.0, 14.5))

    elif name == "external_link":
        p.drawPolyline(QPolygonF([QPointF(13.5, 4.5), QPointF(19.5, 4.5), QPointF(19.5, 10.5)]))
        p.drawLine(QPointF(10.5, 13.5), QPointF(19.5, 4.5))
        path = QPainterPath()
        path.moveTo(18.0, 13.5)
        path.lineTo(18.0, 19.5)
        path.lineTo(4.5, 19.5)
        path.lineTo(4.5, 6.0)
        path.lineTo(10.5, 6.0)
        p.drawPath(path)

    elif name == "win_minimize":
        p.setPen(QPen(col, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap))
        p.drawLine(QPointF(4.5, 12.5), QPointF(19.5, 12.5))

    elif name == "win_maximize":
        p.setPen(QPen(col, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap, Qt.PenJoinStyle.MiterJoin))
        p.drawRect(QRectF(4.5, 4.5, 15.0, 15.0))

    elif name == "win_restore":
        p.setPen(QPen(col, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap, Qt.PenJoinStyle.MiterJoin))
        p.drawRect(QRectF(4.0, 8.0, 12.0, 12.0))
        back = QPainterPath()
        back.moveTo(8.0, 8.0)
        back.lineTo(8.0, 4.0)
        back.lineTo(20.0, 4.0)
        back.lineTo(20.0, 16.0)
        back.lineTo(16.0, 16.0)
        p.drawPath(back)

    elif name == "win_close":
        p.setPen(QPen(col, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap))
        p.drawLine(QPointF(5.0, 5.0), QPointF(19.0, 19.0))
        p.drawLine(QPointF(19.0, 5.0), QPointF(5.0, 19.0))

    p.end()

    icon = QIcon(px)
    _ICON_CACHE[key] = icon
    return icon
