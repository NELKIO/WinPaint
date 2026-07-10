"""
Иконки для WinPaint рисуются программно через QPainter.
Это делает приложение полностью самодостаточным: нет внешних
файлов-картинок, которые могли бы потеряться при копировании.
"""
from PyQt5.QtCore import Qt, QRectF, QPointF, QSize
from PyQt5.QtGui import (QIcon, QPixmap, QPainter, QPen, QBrush, QColor,
                         QPolygonF, QFont, QPainterPath, QLinearGradient)


def _new(size=24):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    return pm, p


def _pen(color="#3b3b3b", w=1.6):
    pen = QPen(QColor(color))
    pen.setWidthF(w)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


# ---------------------------------------------------------------------------
#  Инструменты
# ---------------------------------------------------------------------------

def icon_pencil():
    pm, p = _new()
    p.setPen(_pen("#444", 1.4))
    # корпус карандаша
    body = QPolygonF([QPointF(6, 18), QPointF(15, 9), QPointF(18, 12),
                      QPointF(9, 21), QPointF(6, 18)])
    p.setBrush(QColor("#f4c542"))
    p.drawPolygon(body)
    # грифель
    p.setBrush(QColor("#5a3a1a"))
    p.drawPolygon(QPolygonF([QPointF(6, 18), QPointF(9, 21),
                             QPointF(5, 22), QPointF(6, 18)]))
    # наконечник
    p.setBrush(QColor("#d0d0d0"))
    p.drawPolygon(QPolygonF([QPointF(15, 9), QPointF(18, 12),
                             QPointF(20, 10), QPointF(17, 7)]))
    p.end()
    return QIcon(pm)


def icon_fill():
    pm, p = _new()
    p.setPen(_pen("#444", 1.3))
    p.setBrush(QColor("#cfd8e8"))
    bucket = QPolygonF([QPointF(7, 9), QPointF(16, 9), QPointF(14, 19),
                        QPointF(9, 19)])
    p.drawPolygon(bucket)
    p.setPen(_pen("#444", 1.3))
    p.drawLine(QPointF(11, 4), QPointF(11, 9))
    # капля
    p.setBrush(QColor("#2a7de1"))
    p.setPen(Qt.NoPen)
    path = QPainterPath()
    path.moveTo(18, 13)
    path.cubicTo(20, 16, 20, 19, 18, 20)
    path.cubicTo(16, 19, 16, 16, 18, 13)
    p.drawPath(path)
    p.end()
    return QIcon(pm)


def icon_text():
    pm, p = _new()
    p.setPen(QColor("#2a2a2a"))
    import platform
    font_name = "Georgia" if platform.system() == 'Darwin' else "DejaVu Serif"
    f = QFont(font_name)
    f.setPixelSize(18)
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRectF(0, 0, 24, 24), Qt.AlignCenter, "A")
    p.end()
    return QIcon(pm)


def icon_eraser():
    pm, p = _new()
    p.setPen(_pen("#444", 1.3))
    p.setBrush(QColor("#e9b8c8"))
    poly = QPolygonF([QPointF(5, 16), QPointF(13, 8), QPointF(19, 14),
                      QPointF(11, 22), QPointF(5, 22)])
    p.drawPolygon(poly)
    p.setBrush(QColor("#ffffff"))
    p.drawPolygon(QPolygonF([QPointF(13, 8), QPointF(16, 5),
                             QPointF(22, 11), QPointF(19, 14)]))
    p.end()
    return QIcon(pm)


def icon_picker():
    pm, p = _new()
    # тонкая трубка пипетки (по диагонали)
    p.setPen(_pen("#5a5a5a", 2.6))
    p.drawLine(QPointF(8, 18), QPointF(16, 10))
    # колба-резинка сверху
    p.setPen(_pen("#444", 1.2))
    p.setBrush(QColor("#9aa7b5"))
    p.save()
    p.translate(17, 9)
    p.rotate(45)
    p.drawRoundedRect(QRectF(-3, -4.5, 6, 9), 2.5, 2.5)
    p.restore()
    # капля краски на кончике
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#2a7de1"))
    path = QPainterPath()
    path.moveTo(6, 21)
    path.cubicTo(3.5, 18.5, 4.5, 16.5, 6, 15)
    path.cubicTo(7.5, 16.5, 8.5, 18.5, 6, 21)
    p.drawPath(path)
    p.end()
    return QIcon(pm)


def icon_magnifier():
    pm, p = _new()
    p.setPen(_pen("#444", 2.0))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QRectF(5, 5, 11, 11))
    p.drawLine(QPointF(15, 15), QPointF(20, 20))
    p.setPen(_pen("#444", 1.4))
    p.drawLine(QPointF(8, 10.5), QPointF(13, 10.5))
    p.drawLine(QPointF(10.5, 8), QPointF(10.5, 13))
    p.end()
    return QIcon(pm)


def icon_brush():
    pm, p = _new()
    p.setPen(_pen("#444", 1.3))
    p.setBrush(QColor("#c98a4b"))
    p.drawPolygon(QPolygonF([QPointF(14, 6), QPointF(19, 11),
                             QPointF(12, 18), QPointF(7, 13)]))
    p.setBrush(QColor("#7a4a20"))
    p.drawPolygon(QPolygonF([QPointF(7, 13), QPointF(12, 18),
                             QPointF(7, 21), QPointF(4, 18)]))
    p.setBrush(QColor("#2a7de1"))
    p.setPen(Qt.NoPen)
    p.drawEllipse(QRectF(3, 17, 5, 5))
    p.end()
    return QIcon(pm)


# ---------------------------------------------------------------------------
#  Буфер обмена / изображение
# ---------------------------------------------------------------------------

def icon_paste():
    pm, p = _new(28)
    p.setPen(_pen("#5a6b8c", 1.4))
    p.setBrush(QColor("#caa46a"))
    p.drawRoundedRect(QRectF(5, 6, 14, 18), 2, 2)
    p.setBrush(QColor("#8a6a3a"))
    p.drawRoundedRect(QRectF(9, 3, 6, 4), 1, 1)
    p.setBrush(QColor("#ffffff"))
    p.setPen(_pen("#5a6b8c", 1.2))
    p.drawRect(QRectF(11, 11, 13, 14))
    p.end()
    return QIcon(pm)


def icon_cut():
    pm, p = _new()
    p.setPen(_pen("#444", 1.6))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QRectF(4, 15, 6, 6))
    p.drawEllipse(QRectF(14, 15, 6, 6))
    p.drawLine(QPointF(7, 16), QPointF(18, 5))
    p.drawLine(QPointF(17, 16), QPointF(6, 5))
    p.end()
    return QIcon(pm)


def icon_copy():
    pm, p = _new()
    p.setPen(_pen("#5a6b8c", 1.4))
    p.setBrush(QColor("#ffffff"))
    p.drawRect(QRectF(5, 5, 11, 13))
    p.drawRect(QRectF(9, 9, 11, 13))
    p.end()
    return QIcon(pm)


def icon_select():
    pm, p = _new()
    pen = _pen("#444", 1.4)
    pen.setStyle(Qt.DashLine)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawRect(QRectF(4, 4, 16, 16))
    p.end()
    return QIcon(pm)


def icon_crop():
    pm, p = _new()
    p.setPen(_pen("#444", 1.6))
    p.drawLine(QPointF(7, 3), QPointF(7, 18))
    p.drawLine(QPointF(7, 18), QPointF(21, 18))
    p.drawLine(QPointF(3, 7), QPointF(18, 7))
    p.drawLine(QPointF(18, 7), QPointF(18, 21))
    p.end()
    return QIcon(pm)


def icon_resize():
    pm, p = _new()
    p.setPen(_pen("#444", 1.5))
    p.setBrush(Qt.NoBrush)
    p.drawRect(QRectF(4, 4, 10, 10))
    p.drawRect(QRectF(12, 12, 8, 8))
    p.drawLine(QPointF(14, 4), QPointF(20, 4))
    p.drawLine(QPointF(20, 4), QPointF(20, 10))
    p.end()
    return QIcon(pm)


def icon_rotate():
    pm, p = _new()
    p.setPen(_pen("#444", 1.7))
    p.setBrush(Qt.NoBrush)
    path = QPainterPath()
    path.arcMoveTo(QRectF(5, 5, 14, 14), 60)
    path.arcTo(QRectF(5, 5, 14, 14), 60, 240)
    p.drawPath(path)
    # стрелка
    p.setBrush(QColor("#444"))
    p.drawPolygon(QPolygonF([QPointF(16, 4), QPointF(20, 7),
                             QPointF(14.5, 8.5)]))
    p.end()
    return QIcon(pm)


# ---------------------------------------------------------------------------
#  Фигуры — рисуем сам контур фигуры (это и есть «один в один»)
# ---------------------------------------------------------------------------

def _shape_pixmap(draw_fn, size=22):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(_pen("#3a3a3a", 1.6))
    p.setBrush(Qt.NoBrush)
    draw_fn(p, size)
    p.end()
    return pm


def shape_icon(name):
    s = 22
    m = 3  # отступ

    def line(p, s):
        p.drawLine(QPointF(m, s - m), QPointF(s - m, m))

    def curve(p, s):
        path = QPainterPath()
        path.moveTo(m, s - m)
        path.cubicTo(s * 0.3, m, s * 0.7, s, s - m, m)
        p.drawPath(path)

    def oval(p, s):
        p.drawEllipse(QRectF(m, m + 1, s - 2 * m, s - 2 * m - 2))

    def rect(p, s):
        p.drawRect(QRectF(m, m + 1, s - 2 * m, s - 2 * m - 2))

    def rrect(p, s):
        p.drawRoundedRect(QRectF(m, m + 1, s - 2 * m, s - 2 * m - 2), 4, 4)

    def triangle(p, s):
        p.drawPolygon(QPolygonF([QPointF(s / 2, m), QPointF(s - m, s - m),
                                 QPointF(m, s - m)]))

    def rtriangle(p, s):
        p.drawPolygon(QPolygonF([QPointF(m, m), QPointF(m, s - m),
                                 QPointF(s - m, s - m)]))

    def diamond(p, s):
        p.drawPolygon(QPolygonF([QPointF(s / 2, m), QPointF(s - m, s / 2),
                                 QPointF(s / 2, s - m), QPointF(m, s / 2)]))

    def pentagon(p, s):
        p.drawPolygon(_reg_polygon(5, s, -90))

    def hexagon(p, s):
        p.drawPolygon(_reg_polygon(6, s, 0))

    def arrow_r(p, s):
        c = s / 2
        p.drawPolygon(QPolygonF([
            QPointF(m, c - 3), QPointF(c, c - 3), QPointF(c, m),
            QPointF(s - m, c), QPointF(c, s - m), QPointF(c, c + 3),
            QPointF(m, c + 3)]))

    def arrow_l(p, s):
        c = s / 2
        p.drawPolygon(QPolygonF([
            QPointF(s - m, c - 3), QPointF(c, c - 3), QPointF(c, m),
            QPointF(m, c), QPointF(c, s - m), QPointF(c, c + 3),
            QPointF(s - m, c + 3)]))

    def arrow_u(p, s):
        c = s / 2
        p.drawPolygon(QPolygonF([
            QPointF(c - 3, s - m), QPointF(c - 3, c), QPointF(m, c),
            QPointF(c, m), QPointF(s - m, c), QPointF(c + 3, c),
            QPointF(c + 3, s - m)]))

    def arrow_d(p, s):
        c = s / 2
        p.drawPolygon(QPolygonF([
            QPointF(c - 3, m), QPointF(c - 3, c), QPointF(m, c),
            QPointF(c, s - m), QPointF(s - m, c), QPointF(c + 3, c),
            QPointF(c + 3, m)]))

    def star4(p, s):
        c = s / 2
        p.drawPolygon(QPolygonF([
            QPointF(c, m), QPointF(c + 2, c - 2), QPointF(s - m, c),
            QPointF(c + 2, c + 2), QPointF(c, s - m), QPointF(c - 2, c + 2),
            QPointF(m, c), QPointF(c - 2, c - 2)]))

    def star5(p, s):
        p.drawPolygon(_star_polygon(5, s))

    def star6(p, s):
        p.drawPolygon(_star_polygon(6, s))

    def callout_round(p, s):
        path = QPainterPath()
        path.addRoundedRect(QRectF(m, m, s - 2 * m, s - 2 * m - 4), 4, 4)
        p.drawPath(path)
        p.drawPolygon(QPolygonF([QPointF(7, s - m - 4), QPointF(7, s - m),
                                 QPointF(11, s - m - 4)]))

    def callout_rect(p, s):
        p.drawRect(QRectF(m, m, s - 2 * m, s - 2 * m - 4))
        p.drawPolygon(QPolygonF([QPointF(7, s - m - 4), QPointF(7, s - m),
                                 QPointF(11, s - m - 4)]))

    def callout_cloud(p, s):
        p.drawEllipse(QRectF(m, m + 1, s - 2 * m, s - 2 * m - 6))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(5, s - 9, 3, 3))
        p.drawEllipse(QRectF(8, s - 6, 2, 2))

    def heart(p, s):
        path = QPainterPath()
        c = s / 2
        path.moveTo(c, s - m - 1)
        path.cubicTo(m - 1, s * 0.5, s * 0.18, m, c, s * 0.36)
        path.cubicTo(s * 0.82, m, s - m + 1, s * 0.5, c, s - m - 1)
        p.drawPath(path)

    def lightning(p, s):
        p.drawPolygon(QPolygonF([
            QPointF(12, m), QPointF(7, 12), QPointF(11, 12),
            QPointF(9, s - m), QPointF(16, 9), QPointF(12, 9)]))

    shapes = {
        "line": line, "curve": curve, "oval": oval, "rect": rect,
        "rrect": rrect, "triangle": triangle, "rtriangle": rtriangle,
        "diamond": diamond, "pentagon": pentagon, "hexagon": hexagon,
        "arrow_r": arrow_r, "arrow_l": arrow_l, "arrow_u": arrow_u,
        "arrow_d": arrow_d, "star4": star4, "star5": star5, "star6": star6,
        "callout_round": callout_round, "callout_rect": callout_rect,
        "callout_cloud": callout_cloud, "heart": heart, "lightning": lightning,
    }
    fn = shapes.get(name, rect)
    return QIcon(_shape_pixmap(fn, s))


def _reg_polygon(n, s, start_deg):
    import math
    c = s / 2
    r = s / 2 - 3
    pts = []
    for i in range(n):
        a = math.radians(start_deg + i * 360 / n)
        pts.append(QPointF(c + r * math.cos(a), c + r * math.sin(a)))
    return QPolygonF(pts)


def _star_polygon(points, s):
    import math
    c = s / 2
    r_out = s / 2 - 2
    r_in = r_out * 0.42
    pts = []
    for i in range(points * 2):
        r = r_out if i % 2 == 0 else r_in
        a = math.radians(-90 + i * 180 / points)
        pts.append(QPointF(c + r * math.cos(a), c + r * math.sin(a)))
    return QPolygonF(pts)


def render_app_icon(size=256):
    """Иконка приложения (палитра художника), рисуется в нужном размере."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    s = size / 64.0
    p.scale(s, s)
    grad = QLinearGradient(0, 0, 64, 64)
    grad.setColorAt(0, QColor("#ffd24d"))
    grad.setColorAt(1, QColor("#e89a2b"))
    p.setBrush(QBrush(grad))
    p.setPen(_pen("#9a6a10", 2))
    path = QPainterPath()
    path.addEllipse(QRectF(6, 8, 52, 48))
    hole = QPainterPath()
    hole.addEllipse(QRectF(38, 30, 14, 14))
    p.drawPath(path.subtracted(hole))
    for col, x, y in [("#e23b3b", 16, 18), ("#2a7de1", 30, 14),
                      ("#3bb24a", 44, 18), ("#7a3bd1", 18, 36)]:
        p.setBrush(QColor(col))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(x, y, 8, 8))
    p.end()
    return pm


def app_icon():
    return QIcon(render_app_icon(64))
