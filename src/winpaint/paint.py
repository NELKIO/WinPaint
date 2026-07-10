#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WinPaint — копия Paint из Windows 10 для Linux и macOS (русский интерфейс).
Написано на PyQt5. Самодостаточно, без внешних ресурсов.
"""
import os
import sys
import math

from PyQt5.QtCore import (Qt, QPoint, QPointF, QRect, QRectF, QSize, QTimer,
                          QSizeF)
from PyQt5.QtGui import (QImage, QPixmap, QPainter, QPen, QBrush, QColor,
                         QPolygon, QPolygonF, QPainterPath, QFont, QCursor,
                         QKeySequence, QIcon, QFontMetrics)
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QGridLayout, QLabel, QPushButton,
                             QToolButton, QFrame, QTabWidget, QTabBar, QMenu,
                             QAction, QWidgetAction, QFileDialog, QColorDialog,
                             QMessageBox, QDialog, QLineEdit, QCheckBox,
                             QRadioButton, QSpinBox, QDialogButtonBox, QSlider,
                             QScrollArea, QSizePolicy, QButtonGroup, QStatusBar,
                             QTextEdit, QComboBox, QStyle, QGroupBox)
from PyQt5.QtGui import QTextCharFormat, QTextCursor, QFontDatabase

from . import icons


# ===========================================================================
#  Диалог изменения размера
# ===========================================================================
class ResizeDialog(QDialog):
    def __init__(self, w, h, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Изменение размеров и наклона")
        self.orig_w, self.orig_h = w, h
        self.result_w, self.result_h = w, h

        lay = QVBoxLayout(self)

        box = QGroupBox("Изменить размер")
        g = QGridLayout(box)
        self.rb_percent = QRadioButton("проценты")
        self.rb_pixels = QRadioButton("пиксели")
        self.rb_percent.setChecked(True)
        g.addWidget(self.rb_percent, 0, 0)
        g.addWidget(self.rb_pixels, 0, 1)

        g.addWidget(QLabel("По горизонтали:"), 1, 0)
        self.sp_w = QSpinBox(); self.sp_w.setRange(1, 30000); self.sp_w.setValue(100)
        g.addWidget(self.sp_w, 1, 1)
        g.addWidget(QLabel("По вертикали:"), 2, 0)
        self.sp_h = QSpinBox(); self.sp_h.setRange(1, 30000); self.sp_h.setValue(100)
        g.addWidget(self.sp_h, 2, 1)

        self.cb_aspect = QCheckBox("Сохранять пропорции")
        self.cb_aspect.setChecked(True)
        g.addWidget(self.cb_aspect, 3, 0, 1, 2)
        lay.addWidget(box)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("ОК")
        bb.button(QDialogButtonBox.Cancel).setText("Отмена")
        bb.accepted.connect(self.on_ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        self.rb_percent.toggled.connect(self.switch_mode)
        self.sp_w.valueChanged.connect(lambda v: self.sync(True))
        self.sp_h.valueChanged.connect(lambda v: self.sync(False))
        self._sync_guard = False

    def switch_mode(self):
        self._sync_guard = True
        if self.rb_percent.isChecked():
            self.sp_w.setRange(1, 1000); self.sp_h.setRange(1, 1000)
            self.sp_w.setValue(100); self.sp_h.setValue(100)
        else:
            self.sp_w.setRange(1, 30000); self.sp_h.setRange(1, 30000)
            self.sp_w.setValue(self.orig_w); self.sp_h.setValue(self.orig_h)
        self._sync_guard = False

    def sync(self, from_w):
        if self._sync_guard or not self.cb_aspect.isChecked():
            return
        self._sync_guard = True
        if self.rb_percent.isChecked():
            if from_w:
                self.sp_h.setValue(self.sp_w.value())
            else:
                self.sp_w.setValue(self.sp_h.value())
        else:
            ratio = self.orig_h / self.orig_w
            if from_w:
                self.sp_h.setValue(max(1, round(self.sp_w.value() * ratio)))
            else:
                self.sp_w.setValue(max(1, round(self.sp_h.value() / ratio)))
        self._sync_guard = False

    def on_ok(self):
        if self.rb_percent.isChecked():
            self.result_w = max(1, round(self.orig_w * self.sp_w.value() / 100))
            self.result_h = max(1, round(self.orig_h * self.sp_h.value() / 100))
        else:
            self.result_w = self.sp_w.value()
            self.result_h = self.sp_h.value()
        self.accept()


# ===========================================================================
#  Холст
# ===========================================================================
class Canvas(QWidget):
    def __init__(self, window):
        super().__init__()
        self.win = window
        self.image = QImage(960, 540, QImage.Format_ARGB32)
        self.image.fill(Qt.white)

        self.zoom = 1.0
        self.tool = "brush"          # brush, pencil, eraser, fill, picker,
                                     # magnifier, text, shape, select
        self.brush = "round"
        self.shape = "line"
        self.pen_width = 3
        self.outline_style = "solid"  # solid / none
        self.fill_style = "none"      # solid / none

        self.color1 = QColor(Qt.black)
        self.color2 = QColor(Qt.white)

        self.undo_stack = []
        self.redo_stack = []
        self.max_undo = 40

        self.drawing = False
        self.active_color = self.color1
        self.start_pt = QPoint()
        self.last_pt = QPoint()
        self.temp_image = None        # предпросмотр фигур
        self.cur_button = Qt.LeftButton

        # кривая (двухэтапное рисование)
        self.curve_p1 = None
        self.curve_p2 = None
        self.curve_stage = 0          # 0 — нет, 1 — линия задана, ждём изгиб

        # выделение
        self.sel_rect = None          # QRect в координатах изображения
        self.sel_image = None         # содержимое выделения (QImage)
        self.sel_floating = False     # поднято ли выделение над холстом
        self.sel_moving = False
        self.sel_move_off = QPoint()

        # текст
        self.text_edit = None

        # изменение размера холста перетаскиванием маркеров (как в Paint)
        self.HANDLE = 7               # размер маркера, px (в координатах виджета)
        self.MARGIN = 14              # поле вокруг рисунка для маркеров
        self.canvas_resizing = None   # 'e' | 's' | 'se' | None
        self.canvas_new_size = None   # QSize предпросмотра

        # позиция курсора (для показа площади ластика)
        self.hover_pt = None          # QPoint в координатах изображения

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.CrossCursor)
        self.update_geometry()

        self.ants_timer = QTimer(self)
        self.ants_timer.timeout.connect(self.update)
        self.ants_offset = 0

    # -- геометрия / координаты ------------------------------------------
    def update_geometry(self):
        self.setFixedSize(int(self.image.width() * self.zoom) + self.MARGIN,
                          int(self.image.height() * self.zoom) + self.MARGIN)
        self.update()

    def img_w_px(self):
        return int(self.image.width() * self.zoom)

    def img_h_px(self):
        return int(self.image.height() * self.zoom)

    def handle_rects(self):
        """Прямоугольники маркеров в координатах виджета: восток, юг, угол."""
        w, h, s = self.img_w_px(), self.img_h_px(), self.HANDLE
        return {
            "e": QRect(w + 2, h // 2 - s // 2, s, s),
            "s": QRect(w // 2 - s // 2, h + 2, s, s),
            "se": QRect(w + 2, h + 2, s, s),
        }

    def handle_at(self, pos):
        for name, r in self.handle_rects().items():
            if r.adjusted(-3, -3, 3, 3).contains(pos):
                return name
        return None

    def _tool_cursor(self):
        m = {
            "brush": Qt.CrossCursor, "pencil": Qt.CrossCursor,
            "eraser": Qt.CrossCursor, "fill": Qt.PointingHandCursor,
            "picker": Qt.UpArrowCursor, "magnifier": Qt.PointingHandCursor,
            "text": Qt.IBeamCursor, "shape": Qt.CrossCursor,
            "select": Qt.CrossCursor,
        }
        return m.get(self.tool, Qt.CrossCursor)

    def to_image(self, pos):
        x = int(pos.x() / self.zoom)
        y = int(pos.y() / self.zoom)
        return QPoint(x, y)

    def in_bounds(self, pt):
        return 0 <= pt.x() < self.image.width() and 0 <= pt.y() < self.image.height()

    def constrain_point(self, a, b, shift):
        """С зажатым Shift: линия — ровно по шагам 45°, остальные фигуры —
        правильные (квадрат, круг и т.д.). Без Shift — точка как есть."""
        if not shift:
            return b
        dx, dy = b.x() - a.x(), b.y() - a.y()
        angle_shape = (self.shape == "line" or
                       (self.shape == "curve" and not getattr(self, "_cline_done", False)))
        if angle_shape:
            if dx == 0 and dy == 0:
                return b
            step = math.pi / 4
            ang = round(math.atan2(dy, dx) / step) * step
            dist = math.hypot(dx, dy)
            return QPoint(a.x() + round(dist * math.cos(ang)),
                          a.y() + round(dist * math.sin(ang)))
        s = max(abs(dx), abs(dy))
        return QPoint(a.x() + (s if dx >= 0 else -s),
                      a.y() + (s if dy >= 0 else -s))

    # -- история ----------------------------------------------------------
    def push_undo(self):
        self.undo_stack.append(self.image.copy())
        if len(self.undo_stack) > self.max_undo:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        self.win.mark_dirty()
        self.win.update_actions()

    def undo(self):
        self.commit_text()
        if not self.undo_stack:
            return
        self.commit_selection(silent=True)
        self.redo_stack.append(self.image.copy())
        self.image = self.undo_stack.pop()
        self.clear_selection()
        self.update_geometry()
        self.win.update_actions()
        self.win.update_status_size()

    def redo(self):
        self.commit_text()
        if not self.redo_stack:
            return
        self.undo_stack.append(self.image.copy())
        self.image = self.redo_stack.pop()
        self.clear_selection()
        self.update_geometry()
        self.win.update_actions()
        self.win.update_status_size()

    # -- отрисовка --------------------------------------------------------
    def paintEvent(self, ev):
        p = QPainter(self)
        p.scale(self.zoom, self.zoom)
        base = self.temp_image if self.temp_image is not None else self.image
        p.drawImage(0, 0, base)

        # линии сетки (как в Paint — видны при увеличении от 200%)
        grid_cb = getattr(self.win, "cb_grid", None)
        if grid_cb is not None and grid_cb.isChecked() and self.zoom >= 2:
            p.setPen(QPen(QColor(170, 170, 170), 0))
            w, h = self.image.width(), self.image.height()
            for x in range(w + 1):
                p.drawLine(QPointF(x, 0), QPointF(x, h))
            for y in range(h + 1):
                p.drawLine(QPointF(0, y), QPointF(w, y))

        # плавающее выделение
        if self.sel_image is not None and self.sel_rect is not None and self.sel_floating:
            p.drawImage(self.sel_rect.topLeft(), self.sel_image)

        p.resetTransform()
        # рамка выделения «бегущие муравьи»
        if self.sel_rect is not None:
            r = QRectF(self.sel_rect.x() * self.zoom, self.sel_rect.y() * self.zoom,
                       self.sel_rect.width() * self.zoom,
                       self.sel_rect.height() * self.zoom)
            pen = QPen(Qt.black, 1, Qt.DashLine)
            pen.setDashOffset(self.ants_offset)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRect(r)
            pen2 = QPen(Qt.white, 1, Qt.DashLine)
            pen2.setDashOffset(self.ants_offset + 4)
            p.setPen(pen2)
            p.drawRect(r)

        # маркеры изменения размера холста (белые квадратики с рамкой)
        p.setPen(QPen(QColor("#5a5a5a"), 1))
        p.setBrush(QColor("#ffffff"))
        for r in self.handle_rects().values():
            p.drawRect(r)

        # предпросмотр нового размера холста при перетаскивании
        if self.canvas_resizing and self.canvas_new_size is not None:
            pw = int(self.canvas_new_size.width() * self.zoom)
            ph = int(self.canvas_new_size.height() * self.zoom)
            pen = QPen(QColor("#2a7de1"), 1, Qt.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRect(0, 0, pw, ph))

        # площадь стирания ластика под курсором
        if self.tool == "eraser" and self.hover_pt is not None:
            size = self.eraser_px() * self.zoom
            cx = self.hover_pt.x() * self.zoom
            cy = self.hover_pt.y() * self.zoom
            rect = QRectF(cx - size / 2, cy - size / 2, size, size)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor("#888888"), 1))
            p.drawRect(rect)
            p.setPen(QPen(QColor("#ffffff"), 1, Qt.DashLine))
            p.drawRect(rect)
        p.end()

    # -- мышь -------------------------------------------------------------
    def mousePressEvent(self, ev):
        pt = self.to_image(ev.pos())
        self.cur_button = ev.button()

        # изменение размера холста перетаскиванием маркера — приоритетнее
        if ev.button() == Qt.LeftButton:
            h = self.handle_at(ev.pos())
            if h:
                self.commit_text()
                self.commit_selection()
                self.canvas_resizing = h
                self.canvas_new_size = QSize(self.image.width(), self.image.height())
                return

        if ev.button() == Qt.LeftButton:
            self.active_color = self.color1
            self.bg_color = self.color2
        elif ev.button() == Qt.RightButton:
            self.active_color = self.color2
            self.bg_color = self.color1
        else:
            return

        tool = self.tool

        if tool == "text":
            self.commit_text()
            self.start_text(ev.pos())
            return

        # любой клик вне инструмента «выделение» фиксирует выделение
        if tool != "select":
            self.commit_selection()

        if tool == "picker":
            if self.in_bounds(pt):
                c = QColor(self.image.pixel(pt))
                if ev.button() == Qt.LeftButton:
                    self.win.set_color1(c)
                else:
                    self.win.set_color2(c)
            return

        if tool == "magnifier":
            if ev.button() == Qt.LeftButton:
                self.win.zoom_in()
            else:
                self.win.zoom_out()
            return

        if tool == "fill":
            if self.in_bounds(pt):
                self.push_undo()
                self.flood_fill(pt, self.active_color)
                self.update()
            return

        if tool in ("brush", "pencil", "eraser"):
            self.push_undo()
            self.drawing = True
            self.last_pt = pt
            self.draw_point(pt)
            self.update()
            return

        if tool == "shape":
            if self.shape == "curve":
                self.handle_curve_press(pt)
                return
            self.push_undo()
            self.drawing = True
            self.start_pt = pt
            self.temp_image = self.image.copy()
            return

        if tool == "select":
            if (self.sel_rect is not None and
                    self.sel_rect.contains(pt)):
                # начать перемещение выделения
                if not self.sel_floating:
                    self.lift_selection()
                self.sel_moving = True
                self.sel_move_off = pt - self.sel_rect.topLeft()
            else:
                self.commit_selection()
                self.drawing = True
                self.start_pt = pt
                self.sel_rect = QRect(pt, pt)
            self.update()

    def leaveEvent(self, ev):
        if self.hover_pt is not None:
            self.hover_pt = None
            self.update()
        super().leaveEvent(ev)

    def mouseMoveEvent(self, ev):
        pt = self.to_image(ev.pos())
        self.win.update_status_pos(pt)

        # показываем площадь ластика под курсором
        if self.tool == "eraser":
            self.hover_pt = pt
            self.update()
        elif self.hover_pt is not None:
            self.hover_pt = None
            self.update()

        # идёт изменение размера холста — тянем маркер
        if self.canvas_resizing:
            nw, nh = self.image.width(), self.image.height()
            mx = max(1, int(round(ev.pos().x() / self.zoom)))
            my = max(1, int(round(ev.pos().y() / self.zoom)))
            if self.canvas_resizing in ("e", "se"):
                nw = min(mx, 20000)
            if self.canvas_resizing in ("s", "se"):
                nh = min(my, 20000)
            self.canvas_new_size = QSize(nw, nh)
            self.win.update_status_sel(self.canvas_new_size)
            self.update()
            return

        # курсор-стрелка над маркерами, когда ничего не рисуем
        if not self.drawing and not self.sel_moving:
            hov = self.handle_at(ev.pos())
            if hov == "e":
                self.setCursor(Qt.SizeHorCursor)
            elif hov == "s":
                self.setCursor(Qt.SizeVerCursor)
            elif hov == "se":
                self.setCursor(Qt.SizeFDiagCursor)
            else:
                self.setCursor(self._tool_cursor())

        if self.tool == "select":
            if self.sel_moving and self.sel_rect is not None:
                new_tl = pt - self.sel_move_off
                self.sel_rect.moveTopLeft(new_tl)
                self.update()
                self.win.update_status_sel(self.sel_rect.size())
                return
            if self.drawing:
                self.sel_rect = QRect(self.start_pt, pt).normalized()
                self.win.update_status_sel(self.sel_rect.size())
                self.update()
            return

        if not self.drawing:
            return

        if self.tool in ("brush", "pencil", "eraser"):
            self.draw_line(self.last_pt, pt)
            self.last_pt = pt
            self.update()
        elif self.tool == "shape":
            shift = bool(ev.modifiers() & Qt.ShiftModifier)
            self.temp_image = self.image.copy()
            p = QPainter(self.temp_image)
            p.setRenderHint(QPainter.Antialiasing, self._shape_aa())
            if self.shape == "curve" and self.curve_stage == 1:
                if not getattr(self, "_cline_done", False):
                    ept = self.constrain_point(self.curve_p1, pt, shift)
                else:
                    ept = pt
                self.draw_curve_preview(p, ept)
            else:
                ept = self.constrain_point(self.start_pt, pt, shift)
                self.draw_shape(p, self.start_pt, ept)
            p.end()
            self.win.update_status_sel(QRect(self.start_pt, ept).normalized().size())
            self.update()

    def mouseReleaseEvent(self, ev):
        pt = self.to_image(ev.pos())

        # завершаем изменение размера холста
        if self.canvas_resizing:
            ns = self.canvas_new_size
            self.canvas_resizing = None
            self.canvas_new_size = None
            self.win.update_status_sel(None)
            if ns is not None and (ns.width() != self.image.width() or
                                   ns.height() != self.image.height()):
                self.resize_canvas(ns.width(), ns.height())
            else:
                self.update()
            return

        if self.tool == "select":
            if self.sel_moving:
                self.sel_moving = False
            elif self.drawing:
                self.drawing = False
                self.sel_rect = QRect(self.start_pt, pt).normalized()
                if self.sel_rect.width() < 2 or self.sel_rect.height() < 2:
                    self.clear_selection()
                else:
                    self.sel_rect = self.sel_rect.intersected(self.image.rect())
                    self.sel_image = self.image.copy(self.sel_rect)
                    self.sel_floating = False
                    self.start_ants()
            self.update()
            return

        if not self.drawing:
            return
        self.drawing = False

        if self.tool == "shape":
            if self.shape == "curve":
                shift = bool(ev.modifiers() & Qt.ShiftModifier)
                if self.curve_stage == 1 and not getattr(self, "_cline_done", False):
                    pt = self.constrain_point(self.curve_p1, pt, shift)
                self.handle_curve_release(pt)
            else:
                if self.temp_image is not None:
                    self.image = self.temp_image
                    self.temp_image = None
                self.update()
        self.win.update_status_sel(None)

    # -- рисование примитивов --------------------------------------------
    def make_pen(self, color=None, width=None):
        pen = QPen(color if color else self.active_color)
        pen.setWidthF(width if width else self.pen_width)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        return pen

    def _stroke_aa(self):
        # Карандаш — всегда резкие пиксели (для черчения линии должны быть
        # чёткими при любой толщине, а не размытыми/серыми по краю).
        if self.tool == "pencil":
            return False
        # Кисти остаются мягкими (это художественный инструмент).
        return True

    def _shape_aa(self):
        # Фигуры (линия, прямоугольник, овал и т.д.) — без сглаживания при
        # любой толщине: чёткие чёрные линии для черчения.
        return False

    def draw_point(self, pt):
        p = QPainter(self.image)
        p.setRenderHint(QPainter.Antialiasing, self._stroke_aa())
        self.configure_brush(p)
        p.drawPoint(pt)
        p.end()

    def draw_line(self, a, b):
        p = QPainter(self.image)
        p.setRenderHint(QPainter.Antialiasing, self._stroke_aa())
        self.configure_brush(p)
        p.drawLine(a, b)
        p.end()

    def eraser_px(self):
        # сторона квадратного ластика в пикселях изображения
        return max(4, int(self.pen_width) * 4)

    def configure_brush(self, p):
        if self.tool == "eraser":
            pen = QPen(self.color2)
            pen.setWidthF(self.eraser_px())
            pen.setCapStyle(Qt.SquareCap)
            pen.setJoinStyle(Qt.MiterJoin)
            p.setPen(pen)
            return
        if self.tool == "pencil":
            pen = QPen(self.active_color)
            pen.setWidthF(self.pen_width)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen)
            return

        # кисти
        b = self.brush
        col = QColor(self.active_color)
        w = self.pen_width
        pen = QPen(col)
        pen.setWidthF(w * 2)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)

        if b == "round":
            pass
        elif b == "calligraphy1":
            pen.setCapStyle(Qt.FlatCap)
            pen.setWidthF(w * 2.2)
            p.setPen(pen)
            # имитация наклонного пера
            return
        elif b == "calligraphy2":
            pen.setCapStyle(Qt.SquareCap)
            pen.setWidthF(w * 2.2)
        elif b == "airbrush":
            self._airbrush_pen = True
            pen.setWidthF(w * 2)
        elif b == "oil":
            col2 = QColor(col); col2.setAlpha(160)
            pen = QPen(col2); pen.setWidthF(w * 3)
            pen.setCapStyle(Qt.RoundCap)
        elif b == "crayon":
            col2 = QColor(col); col2.setAlpha(110)
            pen = QPen(col2); pen.setWidthF(w * 2.4)
            pen.setCapStyle(Qt.RoundCap)
        elif b == "marker":
            col2 = QColor(col); col2.setAlpha(120)
            pen = QPen(col2); pen.setWidthF(w * 2.6)
            pen.setCapStyle(Qt.SquareCap)
        elif b == "watercolor":
            col2 = QColor(col); col2.setAlpha(70)
            pen = QPen(col2); pen.setWidthF(w * 3)
            pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)

    # -- фигуры -----------------------------------------------------------
    def shape_pen_brush(self):
        if self.cur_button == Qt.LeftButton:
            outline_c, fill_c = self.color1, self.color2
        else:
            outline_c, fill_c = self.color2, self.color1

        if self.outline_style == "none" and self.fill_style == "solid":
            pen = QPen(fill_c); pen.setWidthF(self.pen_width)
        elif self.outline_style == "none":
            pen = QPen(Qt.NoPen)
        else:
            pen = QPen(outline_c); pen.setWidthF(self.pen_width)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)

        if self.fill_style == "solid":
            brush = QBrush(fill_c)
        else:
            brush = QBrush(Qt.NoBrush)
        return pen, brush

    def draw_shape(self, p, a, b):
        pen, brush = self.shape_pen_brush()
        p.setPen(pen)
        p.setBrush(brush)
        rect = QRect(a, b).normalized()
        x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
        s = self.shape

        if s == "line":
            p.setBrush(Qt.NoBrush)
            p.drawLine(a, b)
            return
        if s == "oval":
            p.drawEllipse(rect); return
        if s == "rect":
            p.drawRect(rect); return
        if s == "rrect":
            p.drawRoundedRect(rect, min(w, h) * 0.2, min(w, h) * 0.2); return

        cx, cy = x + w / 2, y + h / 2
        if s == "triangle":
            poly = QPolygonF([QPointF(cx, y), QPointF(x + w, y + h), QPointF(x, y + h)])
        elif s == "rtriangle":
            poly = QPolygonF([QPointF(x, y), QPointF(x, y + h), QPointF(x + w, y + h)])
        elif s == "diamond":
            poly = QPolygonF([QPointF(cx, y), QPointF(x + w, cy),
                              QPointF(cx, y + h), QPointF(x, cy)])
        elif s == "pentagon":
            poly = self._poly_in_rect(rect, 5, -90)
        elif s == "hexagon":
            poly = self._poly_in_rect(rect, 6, 0)
        elif s in ("arrow_r", "arrow_l", "arrow_u", "arrow_d"):
            poly = self._arrow_poly(s, rect)
        elif s == "star4":
            poly = self._star_in_rect(rect, 4)
        elif s == "star5":
            poly = self._star_in_rect(rect, 5)
        elif s == "star6":
            poly = self._star_in_rect(rect, 6)
        elif s in ("callout_round", "callout_rect", "callout_cloud"):
            self._draw_callout(p, s, rect); return
        elif s == "heart":
            self._draw_heart(p, rect); return
        elif s == "lightning":
            poly = self._lightning_poly(rect)
        else:
            p.drawRect(rect); return
        p.drawPolygon(poly)

    def _poly_in_rect(self, rect, n, start):
        cx, cy = rect.center().x(), rect.center().y()
        rx, ry = rect.width() / 2, rect.height() / 2
        pts = []
        for i in range(n):
            a = math.radians(start + i * 360 / n)
            pts.append(QPointF(cx + rx * math.cos(a), cy + ry * math.sin(a)))
        return QPolygonF(pts)

    def _star_in_rect(self, rect, points):
        cx, cy = rect.center().x(), rect.center().y()
        rx, ry = rect.width() / 2, rect.height() / 2
        ratio = 0.42 if points >= 5 else 0.38
        pts = []
        for i in range(points * 2):
            rr = 1.0 if i % 2 == 0 else ratio
            a = math.radians(-90 + i * 180 / points)
            pts.append(QPointF(cx + rx * rr * math.cos(a),
                               cy + ry * rr * math.sin(a)))
        return QPolygonF(pts)

    def _arrow_poly(self, s, rect):
        x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
        cx, cy = x + w / 2, y + h / 2
        t = min(w, h) * 0.22  # половина толщины тела
        head = min(w, h) * 0.5
        if s == "arrow_r":
            return QPolygonF([QPointF(x, cy - t), QPointF(x + w - head, cy - t),
                              QPointF(x + w - head, y), QPointF(x + w, cy),
                              QPointF(x + w - head, y + h), QPointF(x + w - head, cy + t),
                              QPointF(x, cy + t)])
        if s == "arrow_l":
            return QPolygonF([QPointF(x + w, cy - t), QPointF(x + head, cy - t),
                              QPointF(x + head, y), QPointF(x, cy),
                              QPointF(x + head, y + h), QPointF(x + head, cy + t),
                              QPointF(x + w, cy + t)])
        if s == "arrow_u":
            return QPolygonF([QPointF(cx - t, y + h), QPointF(cx - t, y + head),
                              QPointF(x, y + head), QPointF(cx, y),
                              QPointF(x + w, y + head), QPointF(cx + t, y + head),
                              QPointF(cx + t, y + h)])
        # arrow_d
        return QPolygonF([QPointF(cx - t, y), QPointF(cx - t, y + h - head),
                          QPointF(x, y + h - head), QPointF(cx, y + h),
                          QPointF(x + w, y + h - head), QPointF(cx + t, y + h - head),
                          QPointF(cx + t, y)])

    def _lightning_poly(self, rect):
        x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
        return QPolygonF([
            QPointF(x + w * 0.55, y), QPointF(x + w * 0.2, y + h * 0.5),
            QPointF(x + w * 0.45, y + h * 0.5), QPointF(x + w * 0.3, y + h),
            QPointF(x + w * 0.8, y + h * 0.4), QPointF(x + w * 0.5, y + h * 0.4)])

    def _draw_heart(self, p, rect):
        x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
        path = QPainterPath()
        path.moveTo(x + w / 2, y + h)
        path.cubicTo(x - w * 0.1, y + h * 0.45, x + w * 0.2, y, x + w / 2, y + h * 0.3)
        path.cubicTo(x + w * 0.8, y, x + w * 1.1, y + h * 0.45, x + w / 2, y + h)
        p.drawPath(path)

    def _draw_callout(self, p, s, rect):
        x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
        bubble_h = h * 0.75
        if s == "callout_cloud":
            p.drawEllipse(QRectF(x, y, w, bubble_h))
        else:
            br = QRectF(x, y, w, bubble_h)
            if s == "callout_round":
                p.drawRoundedRect(br, min(w, h) * 0.15, min(w, h) * 0.15)
            else:
                p.drawRect(br)
        tail = QPolygonF([QPointF(x + w * 0.2, y + bubble_h - 1),
                          QPointF(x + w * 0.15, y + h),
                          QPointF(x + w * 0.38, y + bubble_h - 1)])
        b = p.brush()
        p.drawPolygon(tail)

    # -- кривая (двухэтапная) --------------------------------------------
    def handle_curve_press(self, pt):
        if self.curve_stage == 0:
            self.push_undo()
            self.curve_p1 = pt
            self.curve_p2 = pt
            self.start_pt = pt
            self.temp_image = self.image.copy()
            self.drawing = True
            self.curve_stage = 1
        elif self.curve_stage == 1:
            self.drawing = True  # тянем изгиб

    def draw_curve_preview(self, p, pt):
        pen, _ = self.shape_pen_brush()
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        if self.curve_p2 == self.curve_p1 or not self._curve_line_done():
            p.drawLine(self.curve_p1, pt)
        else:
            path = QPainterPath()
            path.moveTo(QPointF(self.curve_p1))
            path.quadTo(QPointF(pt), QPointF(self.curve_p2))
            p.drawPath(path)

    def _curve_line_done(self):
        return getattr(self, "_cline_done", False)

    def handle_curve_release(self, pt):
        if self.curve_stage == 1 and not self._curve_line_done():
            # завершили задание прямой линии
            self.curve_p2 = pt
            self._cline_done = True
            self.drawing = False
            # оставляем превью линии
            self.temp_image = self.image.copy()
            p = QPainter(self.temp_image)
            p.setRenderHint(QPainter.Antialiasing, self._shape_aa())
            pen, _ = self.shape_pen_brush()
            p.setPen(pen); p.setBrush(Qt.NoBrush)
            p.drawLine(self.curve_p1, self.curve_p2)
            p.end()
            self.update()
        elif self.curve_stage == 1 and self._curve_line_done():
            # зафиксировали изгиб
            p = QPainter(self.image)
            p.setRenderHint(QPainter.Antialiasing, self._shape_aa())
            pen, _ = self.shape_pen_brush()
            p.setPen(pen); p.setBrush(Qt.NoBrush)
            path = QPainterPath()
            path.moveTo(QPointF(self.curve_p1))
            path.quadTo(QPointF(pt), QPointF(self.curve_p2))
            p.drawPath(path)
            p.end()
            self.reset_curve()
            self.update()

    def reset_curve(self):
        self.curve_stage = 0
        self.curve_p1 = self.curve_p2 = None
        self._cline_done = False
        self.temp_image = None

    # -- заливка ----------------------------------------------------------
    def flood_fill(self, pt, new_color):
        img = self.image
        w, h = img.width(), img.height()
        x0, y0 = pt.x(), pt.y()
        target = img.pixel(x0, y0)
        nc = new_color.rgba()
        if target == nc:
            return
        pix = img.pixel
        setpix = img.setPixel
        stack = [(x0, y0)]
        while stack:
            x, y = stack.pop()
            if pix(x, y) != target:
                continue
            # идём влево
            xl = x
            while xl > 0 and pix(xl - 1, y) == target:
                xl -= 1
            xr = x
            while xr < w - 1 and pix(xr + 1, y) == target:
                xr += 1
            for xx in range(xl, xr + 1):
                setpix(xx, y, nc)
            if y > 0:
                for xx in range(xl, xr + 1):
                    if pix(xx, y - 1) == target:
                        stack.append((xx, y - 1))
            if y < h - 1:
                for xx in range(xl, xr + 1):
                    if pix(xx, y + 1) == target:
                        stack.append((xx, y + 1))

    # -- выделение --------------------------------------------------------
    def start_ants(self):
        if not self.ants_timer.isActive():
            self.ants_timer.start(120)

    def stop_ants(self):
        self.ants_timer.stop()

    def select_all(self):
        self.commit_selection()
        self.tool = "select"
        self.win.sync_tool_buttons()
        self.sel_rect = self.image.rect()
        self.sel_image = self.image.copy()
        self.sel_floating = False
        self.start_ants()
        self.update()

    def lift_selection(self):
        """Поднять выделение над холстом, очистив исходное место фоном."""
        if self.sel_rect is None or self.sel_floating:
            return
        self.push_undo()
        self.sel_image = self.image.copy(self.sel_rect)
        p = QPainter(self.image)
        p.fillRect(self.sel_rect, self.color2)
        p.end()
        self.sel_floating = True

    def commit_selection(self, silent=False):
        """Зафиксировать плавающее выделение на холсте."""
        if self.sel_rect is not None and self.sel_image is not None and self.sel_floating:
            p = QPainter(self.image)
            p.drawImage(self.sel_rect.topLeft(), self.sel_image)
            p.end()
        self.clear_selection()

    def clear_selection(self):
        self.sel_rect = None
        self.sel_image = None
        self.sel_floating = False
        self.sel_moving = False
        self.stop_ants()
        self.win.update_status_sel(None)
        self.update()

    def delete_selection(self):
        if self.sel_rect is None:
            return
        if not self.sel_floating:
            self.push_undo()
            p = QPainter(self.image)
            p.fillRect(self.sel_rect, self.color2)
            p.end()
        self.clear_selection()

    def copy_selection(self):
        cb = QApplication.clipboard()
        if self.sel_rect is not None and self.sel_image is not None:
            cb.setImage(self.sel_image)
        else:
            cb.setImage(self.image)

    def cut_selection(self):
        if self.sel_rect is None:
            return
        self.copy_selection()
        self.delete_selection()

    def paste(self):
        cb = QApplication.clipboard()
        img = cb.image()
        if img.isNull():
            return
        self.commit_selection()
        self.push_undo()
        img = img.convertToFormat(QImage.Format_ARGB32)
        self.tool = "select"
        self.win.sync_tool_buttons()
        self.sel_image = img
        self.sel_rect = QRect(0, 0, img.width(), img.height())
        self.sel_floating = True
        self.start_ants()
        self.update()

    def crop_to_selection(self):
        if self.sel_rect is None:
            return
        if self.sel_floating:
            self.commit_selection_to_temp()
        self.push_undo()
        rect = self.sel_rect.intersected(self.image.rect())
        self.image = self.image.copy(rect)
        self.clear_selection()
        self.update_geometry()
        self.win.update_status_size()

    def commit_selection_to_temp(self):
        if self.sel_image is not None and self.sel_floating:
            p = QPainter(self.image)
            p.drawImage(self.sel_rect.topLeft(), self.sel_image)
            p.end()
            self.sel_floating = False

    # -- преобразования изображения --------------------------------------
    def resize_image(self, w, h, smooth=True):
        self.commit_selection()
        self.push_undo()
        mode = Qt.SmoothTransformation if smooth else Qt.FastTransformation
        self.image = self.image.scaled(w, h, Qt.IgnoreAspectRatio, mode)
        self.image = self.image.convertToFormat(QImage.Format_ARGB32)
        self.update_geometry()
        self.win.update_status_size()

    def resize_canvas(self, w, h):
        """Изменить размер ХОЛСТА, не растягивая рисунок: существующее
        изображение остаётся в левом верхнем углу, новая область — белая,
        лишнее — обрезается. Это «удлинение» поля, как в Paint."""
        self.commit_selection()
        self.push_undo()
        new_img = QImage(max(1, w), max(1, h), QImage.Format_ARGB32)
        new_img.fill(Qt.white)
        p = QPainter(new_img)
        p.drawImage(0, 0, self.image)
        p.end()
        self.image = new_img
        self.update_geometry()
        self.win.update_status_size()

    def rotate(self, deg):
        self.commit_selection()
        self.push_undo()
        tr = self.image.transformed(self._rot_matrix(deg))
        self.image = tr.convertToFormat(QImage.Format_ARGB32)
        self.update_geometry()
        self.win.update_status_size()

    def _rot_matrix(self, deg):
        from PyQt5.QtGui import QTransform
        t = QTransform()
        t.rotate(deg)
        return t

    def flip(self, horizontal):
        self.commit_selection()
        self.push_undo()
        self.image = self.image.mirrored(horizontal, not horizontal)
        self.image = self.image.convertToFormat(QImage.Format_ARGB32)
        self.update()

    # -- текст ------------------------------------------------------------
    # Размер текста хранится в ПИКСЕЛЯХ изображения (не в пунктах), иначе
    # на экранах с масштабом 150% точечный размер пересчитывается по DPI и
    # текст на картинке выходит крупнее, чем в рамке ввода.
    def image_text_font(self):
        """Шрифт в координатах изображения (для впечатывания в картинку)."""
        f = QFont(self.win.text_font_family)
        f.setPixelSize(max(1, int(self.win.text_font_size)))
        f.setBold(self.win.text_bold)
        f.setItalic(self.win.text_italic)
        f.setUnderline(self.win.text_underline)
        return f

    def editor_text_font(self):
        """Тот же шрифт, но масштабированный под текущий зум — рамка ввода
        выглядит ровно так же, как итоговый текст на картинке (WYSIWYG)."""
        f = self.image_text_font()
        f.setPixelSize(max(1, int(round(self.win.text_font_size * self.zoom))))
        return f

    def start_text(self, pos):
        ipt = self.to_image(pos)
        self.text_edit = QTextEdit(self)
        self.text_edit.setStyleSheet(
            "QTextEdit{background:transparent;border:1px dashed #2a7de1;}")
        self.text_edit.setFont(self.editor_text_font())
        pal = self.text_edit.palette()
        pal.setColor(self.text_edit.viewport().backgroundRole(), Qt.transparent)
        from PyQt5.QtGui import QPalette
        pal.setColor(QPalette.Text, self.color1)
        self.text_edit.setPalette(pal)
        self.text_edit.setTextColor(self.color1)
        self.text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.text_edit.setLineWrapMode(QTextEdit.NoWrap)
        self.text_edit.move(int(ipt.x() * self.zoom), int(ipt.y() * self.zoom))
        self.text_edit.show()
        self.text_edit.setFocus()
        self.win.show_text_bar()
        self._text_pos = ipt
        self.text_edit.textChanged.connect(self.fit_text_edit)
        self.fit_text_edit()

    def fit_text_edit(self):
        """Поле ввода текста подстраивается под шрифт и содержимое."""
        te = self.text_edit
        if te is None:
            return
        doc = te.document()
        doc.setTextWidth(-1)
        fm = te.fontMetrics()
        w = max(int(doc.idealWidth()) + fm.averageCharWidth() * 2 + 16,
                int(120 * self.zoom))
        h = max(int(doc.size().height()) + 12, int(fm.height() + 14))
        # не вылезаем за пределы холста
        max_w = max(60, self.img_w_px() - te.x())
        max_h = max(40, self.img_h_px() - te.y())
        te.resize(min(w, max_w + self.MARGIN), min(h, max_h + self.MARGIN))

    def commit_text(self):
        if self.text_edit is None:
            return
        te = self.text_edit
        self.text_edit = None          # сразу, чтобы не было повторного входа
        txt = te.toPlainText()
        if txt.strip():
            self.push_undo()
            p = QPainter(self.image)
            p.setRenderHint(QPainter.TextAntialiasing, True)
            p.setPen(self.color1)
            # рисуем шрифтом в пикселях изображения — размер совпадает с рамкой
            p.setFont(self.image_text_font())
            rect = QRectF(self._text_pos.x(), self._text_pos.y(),
                          te.width() / self.zoom + 4,
                          te.height() / self.zoom + 100)
            p.drawText(rect, Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop, txt)
            p.end()
        self._destroy_widget(te)
        self.update()

    def cancel_text(self):
        if self.text_edit is None:
            return
        te = self.text_edit
        self.text_edit = None
        self._destroy_widget(te)
        self.update()

    def _destroy_widget(self, wdg):
        wdg.hide()
        wdg.setParent(None)
        wdg.deleteLater()
        self.win.hide_text_bar()

    # -- новый / загрузка -------------------------------------------------
    def new_image(self, w=960, h=540):
        self.cancel_text()
        self.clear_selection()
        self.image = QImage(w, h, QImage.Format_ARGB32)
        self.image.fill(Qt.white)
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.zoom = 1.0
        self.update_geometry()
        self.win.update_status_size()
        self.win.update_zoom_label()

    def load_image(self, img):
        self.cancel_text()
        self.clear_selection()
        self.image = img.convertToFormat(QImage.Format_ARGB32)
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.update_geometry()
        self.win.update_status_size()

    def set_zoom(self, z):
        self.commit_text()
        self.zoom = max(0.1, min(z, 8.0))
        self.update_geometry()
        self.win.update_zoom_label()


# ===========================================================================
#  Виджеты ленты (ribbon)
# ===========================================================================
class RibbonGroup(QWidget):
    """Группа на ленте: содержимое сверху, подпись снизу."""
    def __init__(self, title):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(2, 1, 2, 0)
        outer.setSpacing(0)
        self.content = QWidget()
        self.content_layout = QHBoxLayout(self.content)
        self.content_layout.setContentsMargins(1, 1, 1, 1)
        self.content_layout.setSpacing(2)
        outer.addWidget(self.content, 1)
        lbl = QLabel(title)
        lbl.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        lbl.setStyleSheet("color:#555;font-size:10px;")
        outer.addWidget(lbl, 0)

    def add(self, w):
        self.content_layout.addWidget(w)
        return w


def big_button(text, icon=None, width=58):
    b = QToolButton()
    b.setText(text)
    if icon:
        b.setIcon(icon)
        b.setIconSize(QSize(26, 26))
    b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
    b.setAutoRaise(True)
    b.setFixedWidth(width)
    b.setMinimumHeight(54)
    b.setStyleSheet("QToolButton{font-size:11px;}")
    return b


def small_button(text, icon=None):
    b = QToolButton()
    b.setText(text)
    if icon:
        b.setIcon(icon)
        b.setIconSize(QSize(16, 16))
    b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    b.setAutoRaise(True)
    b.setStyleSheet("text-align:left;padding:1px 4px;")
    return b


def vline():
    f = QFrame()
    f.setFrameShape(QFrame.VLine)
    f.setFrameShadow(QFrame.Sunken)
    f.setStyleSheet("color:#d8d8d8;")
    return f


# ===========================================================================
#  Главное окно
# ===========================================================================
class PaintWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.canvas = Canvas(self)
        self.file_path = None
        self.dirty = False

        # параметры текста
        self.text_font_family = "DejaVu Sans"
        self.text_font_size = 14
        self.text_bold = False
        self.text_italic = False
        self.text_underline = False

        self.tool_buttons = {}
        self.brush_actions = {}

        self.setWindowIcon(icons.app_icon())
        self.build_ui()
        self.update_title()
        self.update_status_size()
        self.update_zoom_label()
        self.update_actions()
        self.setMinimumSize(720, 460)

    # -- построение интерфейса -------------------------------------------
    def build_ui(self):
        central = QWidget()
        v = QVBoxLayout(central)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        self.build_statusbar()
        self.build_ribbon(v)
        self.build_text_bar(v)

        # область прокрутки с холстом.
        # widgetResizable=True + holder с центрирующим layout: когда холст
        # меньше окна — он по центру; когда больше (после увеличения) — holder
        # растёт под него и появляются полосы прокрутки, по которым можно
        # перемещаться по увеличенному рисунку.
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setStyleSheet("QScrollArea{background:#c8d0e0;border:none;}")
        holder = QWidget()
        hl = QHBoxLayout(holder)
        hl.setContentsMargins(12, 12, 12, 12)
        # holder обязан вырастать минимум до размера холста — тогда при
        # увеличении появляются полосы прокрутки на всю длину рисунка
        hl.setSizeConstraint(QHBoxLayout.SetMinimumSize)
        hl.addWidget(self.canvas, 0, Qt.AlignCenter)
        holder.setStyleSheet("background:#c8d0e0;")
        self.scroll.setWidget(holder)
        v.addWidget(self.scroll, 1)

        self.setCentralWidget(central)
        self.build_shortcuts()
        self.apply_style()

    def build_quick_access(self):
        """Панель быстрого доступа (сохранить/отменить/вернуть) в строке вкладок."""
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(4, 2, 8, 2)
        h.setSpacing(2)
        self.act_save_q = self._qbtn(self.style().standardIcon(QStyle.SP_DialogSaveButton),
                                     "Сохранить (Ctrl+S)", self.save)
        self.act_undo_q = self._qbtn(self.style().standardIcon(QStyle.SP_ArrowBack),
                                     "Отменить (Ctrl+Z)", self.canvas.undo)
        self.act_redo_q = self._qbtn(self.style().standardIcon(QStyle.SP_ArrowForward),
                                     "Вернуть (Ctrl+Y)", self.canvas.redo)
        h.addWidget(self.act_save_q)
        h.addWidget(self.act_undo_q)
        h.addWidget(self.act_redo_q)
        return bar

    def _qbtn(self, icon, tip, slot):
        b = QToolButton()
        b.setIcon(icon)
        b.setIconSize(QSize(16, 16))
        b.setToolTip(tip)
        b.setAutoRaise(True)
        b.clicked.connect(slot)
        return b

    def build_ribbon(self, v):
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        # вкладка «Файл» — особая
        self.tabs.addTab(QWidget(), "Файл")
        self.tabs.addTab(self._ribbon_scroll(self.build_home_tab()), "Главная")
        self.tabs.addTab(self._ribbon_scroll(self.build_view_tab()), "Вид")
        self.tabs.setCurrentIndex(1)
        self._prev_tab = 1
        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.tabs.setMaximumHeight(124)
        # кнопки сохранить/назад/вперёд — в той же строке, что и вкладки
        self.tabs.setCornerWidget(self.build_quick_access(), Qt.TopRightCorner)
        v.addWidget(self.tabs)

    # ---- список основных шрифтов (без «миллиона» системных) ----
    def available_fonts(self):
        """Короткий список основных шрифтов, реально установленных в системе."""
        preferred = [
            "Times New Roman", "Arial", "Courier New", "Georgia",
            "Verdana", "Tahoma", "Trebuchet MS", "Comic Sans MS", "Impact",
            "DejaVu Sans", "DejaVu Serif", "DejaVu Sans Mono",
            "Liberation Serif", "Liberation Sans", "Liberation Mono",
            "Ubuntu", "Noto Sans",
            # macOS
            "Helvetica Neue", "Helvetica", "San Francisco", "Menlo",
            "SF Pro", "Avenir", "Optima",
        ]
        installed = set(QFontDatabase().families())
        result = [f for f in preferred if f in installed]
        # уберём дубли-аналоги, если есть «настоящие» MS-шрифты
        if "Times New Roman" in result and "Liberation Serif" in result:
            result.remove("Liberation Serif")
        if "Arial" in result and "Liberation Sans" in result:
            result.remove("Liberation Sans")
        if "Courier New" in result and "Liberation Mono" in result:
            result.remove("Liberation Mono")
        if not result:                       # подстраховка
            result = sorted(installed)[:10] or ["Sans Serif"]
        return result

    # ---- контекстная панель форматирования текста ----
    def build_text_bar(self, v):
        bar = QFrame()
        bar.setStyleSheet("QFrame{background:#eef3fb;border-bottom:1px solid #cdd8ea;}")
        h = QHBoxLayout(bar)
        h.setContentsMargins(8, 3, 8, 3)
        h.setSpacing(6)

        h.addWidget(QLabel("Шрифт:"))
        self.txt_font = QComboBox()
        self.txt_font.setMaximumWidth(190)
        fonts = self.available_fonts()
        self.txt_font.addItems(fonts)
        if self.text_font_family not in fonts and fonts:
            self.text_font_family = fonts[0]
        self.txt_font.setCurrentText(self.text_font_family)
        self.txt_font.currentTextChanged.connect(lambda _: self.apply_text_format())
        h.addWidget(self.txt_font)

        h.addWidget(QLabel("Размер:"))
        self.txt_size = QComboBox()
        self.txt_size.setEditable(True)
        self.txt_size.addItems([str(s) for s in
                                (8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28,
                                 32, 36, 48, 72)])
        self.txt_size.setCurrentText(str(self.text_font_size))
        self.txt_size.setMaximumWidth(64)
        self.txt_size.currentTextChanged.connect(lambda _: self.apply_text_format())
        h.addWidget(self.txt_size)

        self.txt_bold = QToolButton(); self.txt_bold.setText("Ж")
        self.txt_bold.setCheckable(True); self.txt_bold.setToolTip("Полужирный")
        f = self.txt_bold.font(); f.setBold(True); self.txt_bold.setFont(f)
        self.txt_bold.toggled.connect(lambda _: self.apply_text_format())
        h.addWidget(self.txt_bold)

        self.txt_italic = QToolButton(); self.txt_italic.setText("К")
        self.txt_italic.setCheckable(True); self.txt_italic.setToolTip("Курсив")
        f = self.txt_italic.font(); f.setItalic(True); self.txt_italic.setFont(f)
        self.txt_italic.toggled.connect(lambda _: self.apply_text_format())
        h.addWidget(self.txt_italic)

        self.txt_underline = QToolButton(); self.txt_underline.setText("Ч")
        self.txt_underline.setCheckable(True); self.txt_underline.setToolTip("Подчёркнутый")
        f = self.txt_underline.font(); f.setUnderline(True); self.txt_underline.setFont(f)
        self.txt_underline.toggled.connect(lambda _: self.apply_text_format())
        h.addWidget(self.txt_underline)

        h.addWidget(QLabel("  (выберите текст и нажмите для применения)"))
        h.addStretch(1)

        for b in (self.txt_bold, self.txt_italic, self.txt_underline):
            b.setFixedSize(28, 26)
            b.setStyleSheet("QToolButton{border:1px solid #c0ccdf;border-radius:3px;}"
                            "QToolButton:checked{background:#cfe3fb;border-color:#7fb0ec;}")

        self.text_bar = bar
        bar.setVisible(False)
        v.addWidget(bar)

    def show_text_bar(self):
        # синхронизируем контролы с текущими настройками текста
        for w in (self.txt_font, self.txt_size, self.txt_bold,
                  self.txt_italic, self.txt_underline):
            w.blockSignals(True)
        self.txt_font.setCurrentText(self.text_font_family)
        self.txt_size.setCurrentText(str(self.text_font_size))
        self.txt_bold.setChecked(self.text_bold)
        self.txt_italic.setChecked(self.text_italic)
        self.txt_underline.setChecked(self.text_underline)
        for w in (self.txt_font, self.txt_size, self.txt_bold,
                  self.txt_italic, self.txt_underline):
            w.blockSignals(False)
        self.text_bar.setVisible(True)

    def hide_text_bar(self):
        self.text_bar.setVisible(False)

    def remember_text_settings(self):
        """Считать настройки из панели в значения по умолчанию."""
        self.text_font_family = self.txt_font.currentText()
        try:
            size = int(float(self.txt_size.currentText()))
        except ValueError:
            size = self.text_font_size
        self.text_font_size = max(4, min(size, 400))
        self.text_bold = self.txt_bold.isChecked()
        self.text_italic = self.txt_italic.isChecked()
        self.text_underline = self.txt_underline.isChecked()

    def apply_text_format(self):
        self.remember_text_settings()
        te = self.canvas.text_edit
        if te is None:
            return
        # шрифт рамки = масштабированный под зум (WYSIWYG)
        f = self.canvas.editor_text_font()
        cur = te.textCursor()
        had_sel = cur.hasSelection()
        if not had_sel:
            te.selectAll()
        fmt = QTextCharFormat()
        fmt.setFont(f)
        te.mergeCurrentCharFormat(fmt)
        te.setFont(f)            # шрифт по умолчанию для дальнейшего ввода
        if not had_sel:
            cur.movePosition(QTextCursor.End)
            te.setTextCursor(cur)
        self.canvas.fit_text_edit()
        te.setFocus()

    def _ribbon_scroll(self, page):
        """Лента в горизонтальной прокрутке: на узких экранах группы не
        сплющиваются, а появляется полоса прокрутки."""
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.NoFrame)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        sa.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sa.setWidget(page)
        sa.setStyleSheet("QScrollArea{background:#fbfbfc;border:none;}")
        return sa

    def on_tab_changed(self, idx):
        if idx == 0:
            self.tabs.blockSignals(True)
            self.tabs.setCurrentIndex(self._prev_tab)
            self.tabs.blockSignals(False)
            self.show_file_menu()
        else:
            self._prev_tab = idx

    def show_file_menu(self):
        m = QMenu(self)
        m.addAction("Создать", self.new_file, QKeySequence.New)
        m.addAction("Открыть…", self.open_file, QKeySequence.Open)
        m.addAction("Сохранить", self.save, QKeySequence.Save)
        m.addAction("Сохранить как…", self.save_as)
        m.addSeparator()
        m.addAction("Печать…", self.print_image, QKeySequence.Print)
        m.addSeparator()
        m.addAction("Выход", self.close, QKeySequence.Quit)
        rect = self.tabs.tabBar().tabRect(0)
        m.exec_(self.tabs.tabBar().mapToGlobal(rect.bottomLeft()))

    # ---- вкладка «Главная» ----
    def build_home_tab(self):
        page = QWidget()
        h = QHBoxLayout(page)
        h.setContentsMargins(2, 2, 2, 0)
        h.setSpacing(2)

        # Буфер обмена
        g = RibbonGroup("Буфер обмена")
        self.btn_paste = big_button("Вставить", icons.icon_paste())
        self.btn_paste.clicked.connect(self.canvas.paste)
        g.add(self.btn_paste)
        col = QWidget(); cv = QVBoxLayout(col); cv.setContentsMargins(0, 4, 0, 0); cv.setSpacing(1)
        b_cut = small_button("Вырезать", icons.icon_cut()); b_cut.clicked.connect(self.canvas.cut_selection)
        b_copy = small_button("Копировать", icons.icon_copy()); b_copy.clicked.connect(self.canvas.copy_selection)
        cv.addWidget(b_cut); cv.addWidget(b_copy); cv.addStretch(1)
        g.add(col)
        h.addWidget(g); h.addWidget(vline())

        # Изображение
        g = RibbonGroup("Изображение")
        b_sel = big_button("Выделить", icons.icon_select(), width=78)
        b_sel.setPopupMode(QToolButton.MenuButtonPopup)
        sel_menu = QMenu(b_sel)
        sel_menu.addAction("Прямоугольная область", lambda: self.set_tool("select"))
        sel_menu.addAction("Выделить всё\tCtrl+A", self.canvas.select_all)
        sel_menu.addSeparator()
        sel_menu.addAction("Удалить\tDel", self.canvas.delete_selection)
        b_sel.setMenu(sel_menu)
        b_sel.clicked.connect(lambda: self.set_tool("select"))
        g.add(b_sel)
        col = QWidget(); cv = QVBoxLayout(col); cv.setContentsMargins(0, 4, 0, 0); cv.setSpacing(1)
        b_crop = small_button("Обрезать", icons.icon_crop()); b_crop.clicked.connect(self.canvas.crop_to_selection)
        b_rsz = small_button("Изменить размер", icons.icon_resize()); b_rsz.clicked.connect(self.open_resize)
        b_rot = small_button("Повернуть", icons.icon_rotate())
        b_rot.setPopupMode(QToolButton.InstantPopup)
        rot_menu = QMenu(b_rot)
        rot_menu.addAction("Повернуть на 90° по часовой", lambda: self.canvas.rotate(90))
        rot_menu.addAction("Повернуть на 90° против часовой", lambda: self.canvas.rotate(-90))
        rot_menu.addAction("Повернуть на 180°", lambda: self.canvas.rotate(180))
        rot_menu.addSeparator()
        rot_menu.addAction("Отразить по горизонтали", lambda: self.canvas.flip(True))
        rot_menu.addAction("Отразить по вертикали", lambda: self.canvas.flip(False))
        b_rot.setMenu(rot_menu)
        cv.addWidget(b_crop); cv.addWidget(b_rsz); cv.addWidget(b_rot)
        g.add(col)
        h.addWidget(g); h.addWidget(vline())

        # Инструменты
        g = RibbonGroup("Инструменты")
        grid_w = QWidget(); grid = QGridLayout(grid_w)
        grid.setContentsMargins(0, 0, 0, 0); grid.setSpacing(1)
        tools = [
            ("pencil", "Карандаш", icons.icon_pencil()),
            ("fill", "Заливка цветом", icons.icon_fill()),
            ("text", "Текст", icons.icon_text()),
            ("eraser", "Ластик", icons.icon_eraser()),
            ("picker", "Выбор цвета", icons.icon_picker()),
            ("magnifier", "Масштаб", icons.icon_magnifier()),
        ]
        for i, (key, tip, ic) in enumerate(tools):
            tb = QToolButton()
            tb.setIcon(ic); tb.setIconSize(QSize(18, 18))
            tb.setToolTip(tip); tb.setAutoRaise(True); tb.setCheckable(True)
            tb.setFixedSize(26, 26)
            tb.clicked.connect(lambda _, k=key: self.set_tool(k))
            grid.addWidget(tb, i // 3, i % 3)
            self.tool_buttons[key] = tb
        g.add(grid_w)
        h.addWidget(g); h.addWidget(vline())

        # Кисти (подпись группы — снизу; на самой кнопке текст не дублируем)
        g = RibbonGroup("Кисти")
        self.btn_brushes = big_button("", icons.icon_brush())
        self.btn_brushes.setToolTip("Кисти")
        self.btn_brushes.setPopupMode(QToolButton.InstantPopup)
        self.btn_brushes.setMenu(self.build_brush_menu())
        g.add(self.btn_brushes)
        self.tool_buttons["brush"] = self.btn_brushes
        h.addWidget(g); h.addWidget(vline())

        # Фигуры
        g = RibbonGroup("Фигуры")
        shapes_w = QWidget(); sg = QGridLayout(shapes_w)
        sg.setContentsMargins(0, 0, 0, 0); sg.setSpacing(1)
        shape_list = [
            "line", "curve", "oval", "rect", "rrect", "triangle", "rtriangle",
            "diamond", "pentagon", "hexagon", "arrow_r", "arrow_l", "arrow_u",
            "arrow_d", "star4", "star5", "star6", "callout_round",
            "callout_rect", "callout_cloud", "heart", "lightning",
        ]
        self.shape_buttons = {}
        for i, name in enumerate(shape_list):
            tb = QToolButton()
            tb.setIcon(icons.shape_icon(name)); tb.setIconSize(QSize(18, 18))
            tb.setAutoRaise(True); tb.setCheckable(True)
            tb.setFixedSize(22, 22)
            tb.clicked.connect(lambda _, n=name: self.set_shape(n))
            sg.addWidget(tb, i // 8, i % 8)
            self.shape_buttons[name] = tb
        g.add(shapes_w)

        # Контур / Заливка
        of_col = QWidget(); ov = QVBoxLayout(of_col)
        ov.setContentsMargins(2, 2, 2, 2); ov.setSpacing(2)
        b_outline = small_button("Контур")
        b_outline.setPopupMode(QToolButton.InstantPopup)
        om = QMenu(b_outline)
        om.addAction("Нет контура", lambda: self.set_outline("none"))
        om.addAction("Сплошной цвет", lambda: self.set_outline("solid"))
        b_outline.setMenu(om)
        b_fill = small_button("Заливка")
        b_fill.setPopupMode(QToolButton.InstantPopup)
        fm = QMenu(b_fill)
        fm.addAction("Нет заливки", lambda: self.set_fill("none"))
        fm.addAction("Сплошной цвет", lambda: self.set_fill("solid"))
        b_fill.setMenu(fm)
        ov.addWidget(b_outline); ov.addWidget(b_fill); ov.addStretch(1)
        g.add(of_col)
        h.addWidget(g); h.addWidget(vline())

        # Размер (толщина линии). Подпись — только название группы снизу.
        g = RibbonGroup("Размер")
        b_size = big_button("")
        b_size.setToolTip("Толщина линии")
        b_size.setPopupMode(QToolButton.InstantPopup)
        b_size.setMenu(self.build_size_menu())
        self.btn_size = b_size
        g.add(b_size)
        h.addWidget(g); h.addWidget(vline())

        # Цвета
        g = RibbonGroup("Цвета")
        self.btn_color1 = self._color_indicator("Цвет 1", self.canvas.color1)
        self.btn_color2 = self._color_indicator("Цвет 2", self.canvas.color2)
        c1w = QWidget(); c1l = QVBoxLayout(c1w); c1l.setContentsMargins(0, 0, 0, 0); c1l.setSpacing(0)
        c1l.addWidget(self.btn_color1[0], 0, Qt.AlignHCenter)
        c1l.addWidget(self.btn_color1[1], 0, Qt.AlignHCenter)
        c2w = QWidget(); c2l = QVBoxLayout(c2w); c2l.setContentsMargins(0, 0, 0, 0); c2l.setSpacing(0)
        c2l.addWidget(self.btn_color2[0], 0, Qt.AlignHCenter)
        c2l.addWidget(self.btn_color2[1], 0, Qt.AlignHCenter)
        g.add(c1w); g.add(c2w)
        g.add(self.build_palette())
        b_edit = big_button("Изменение\nцветов", width=70)
        b_edit.clicked.connect(self.edit_colors)
        g.add(b_edit)
        h.addWidget(g)
        h.addStretch(1)

        # инструмент по умолчанию — Карандаш (как в Windows Paint).
        # Важно: фигуру задаём напрямую, НЕ выбирая её, иначе кнопка фигуры
        # подсветится, а рисоваться будет другой инструмент (рассинхрон).
        self.canvas.shape = "line"
        self.set_tool("pencil")
        self._update_size_button(self.canvas.pen_width)
        return page

    def _color_indicator(self, label, color):
        sw = QToolButton()
        sw.setFixedSize(30, 30)
        sw.setAutoRaise(True)
        self._paint_swatch(sw, color)
        lbl = QLabel(label)
        lbl.setStyleSheet("font-size:11px;color:#444;")
        lbl.setAlignment(Qt.AlignHCenter)
        if "1" in label:
            sw.clicked.connect(lambda: self.edit_colors())
        else:
            sw.clicked.connect(lambda: self.edit_color2())
        return sw, lbl

    def _paint_swatch(self, btn, color):
        pm = QPixmap(28, 28)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setPen(QPen(QColor("#808080"), 1))
        p.setBrush(color)
        p.drawRect(2, 2, 24, 24)
        p.end()
        btn.setIcon(QIcon(pm))
        btn.setIconSize(QSize(28, 28))

    def build_palette(self):
        w = QWidget()
        grid = QGridLayout(w)
        grid.setContentsMargins(0, 2, 0, 2)
        grid.setSpacing(1)
        row1 = ["#000000", "#7f7f7f", "#880015", "#ed1c24", "#ff7f27",
                "#fff200", "#22b14c", "#00a2e8", "#3f48cc", "#a349a4"]
        row2 = ["#ffffff", "#c3c3c3", "#b97a57", "#ffaec9", "#ffc90e",
                "#efe4b0", "#b5e61d", "#99d9ea", "#7092be", "#c8bfe7"]
        self.custom_swatches = []
        for r, row in enumerate((row1, row2)):
            for c, hexcol in enumerate(row):
                btn = self._palette_btn(QColor(hexcol))
                grid.addWidget(btn, r, c)
        # пустые ячейки для пользовательских цветов
        for c in range(10):
            btn = self._palette_btn(QColor(Qt.white), custom=True)
            grid.addWidget(btn, 2, c)
            self.custom_swatches.append(btn)
        return w

    def _palette_btn(self, color, custom=False):
        btn = QToolButton()
        btn.setFixedSize(15, 15)
        btn.setAutoRaise(True)
        self._paint_palette(btn, color)
        btn._color = color
        btn.clicked.connect(lambda: self.set_color1(btn._color))
        btn.setContextMenuPolicy(Qt.CustomContextMenu)
        btn.customContextMenuRequested.connect(lambda _: self.set_color2(btn._color))
        return btn

    def _paint_palette(self, btn, color):
        pm = QPixmap(13, 13)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setPen(QPen(QColor("#a0a0a0"), 1))
        p.setBrush(color)
        p.drawRect(0, 0, 12, 12)
        p.end()
        btn.setIcon(QIcon(pm))
        btn.setIconSize(QSize(13, 13))

    def build_brush_menu(self):
        m = QMenu(self)
        brushes = [
            ("round", "Кисть"),
            ("calligraphy1", "Каллиграфическая кисть 1"),
            ("calligraphy2", "Каллиграфическая кисть 2"),
            ("airbrush", "Распылитель"),
            ("oil", "Масляная кисть"),
            ("crayon", "Восковой мелок"),
            ("marker", "Маркер"),
            ("watercolor", "Акварель"),
        ]
        for key, name in brushes:
            act = m.addAction(name, lambda k=key: self.set_brush(k))
            self.brush_actions[key] = act
        return m

    def build_size_menu(self):
        m = QMenu(self)
        for px in (1, 3, 5, 8, 12):
            pm = QPixmap(120, 20)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing, px > 1)
            pen = QPen(Qt.black); pen.setWidth(px); pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawLine(8, 10, 112, 10)
            p.end()
            word = "пиксель" if px == 1 else ("пикселя" if px < 5 else "пикселей")
            act = QAction(QIcon(pm), "%d %s" % (px, word), self)
            act.triggered.connect(lambda _, w=px: self.set_pen_width(w))
            m.addAction(act)
        return m

    # ---- вкладка «Вид» ----
    def build_view_tab(self):
        page = QWidget()
        h = QHBoxLayout(page)
        h.setContentsMargins(2, 2, 2, 0); h.setSpacing(2)

        g = RibbonGroup("Масштаб")
        b_in = big_button("Увеличить", icons.icon_magnifier(), width=72); b_in.clicked.connect(self.zoom_in)
        b_out = big_button("Уменьшить", icons.icon_magnifier(), width=72); b_out.clicked.connect(self.zoom_out)
        b_100 = big_button("100%"); b_100.clicked.connect(lambda: self.canvas.set_zoom(1.0))
        g.add(b_in); g.add(b_out); g.add(b_100)
        h.addWidget(g); h.addWidget(vline())

        g = RibbonGroup("Показать или скрыть")
        self.cb_status = QCheckBox("Строка состояния"); self.cb_status.setChecked(True)
        self.cb_status.toggled.connect(lambda v: self.statusBar().setVisible(v))
        self.cb_grid = QCheckBox("Линии сетки")
        self.cb_grid.toggled.connect(self.on_toggle_grid)
        col = QWidget(); cv = QVBoxLayout(col); cv.setContentsMargins(4, 4, 4, 4)
        cv.addWidget(self.cb_status); cv.addWidget(self.cb_grid); cv.addStretch(1)
        g.add(col)
        h.addWidget(g); h.addWidget(vline())

        g = RibbonGroup("Экран")
        b_full = big_button("Во весь\nэкран"); b_full.clicked.connect(self.toggle_fullscreen)
        g.add(b_full)
        h.addWidget(g)
        h.addStretch(1)
        return page

    def on_toggle_grid(self, on):
        # сетка видна только при увеличении; подскажем и увеличим, если мелко
        if on and self.canvas.zoom < 2:
            self.canvas.set_zoom(4.0)
            self.statusBar().showMessage(
                "Линии сетки видны при увеличении (200% и больше)", 4000)
        self.canvas.update()

    # -- строка состояния -------------------------------------------------
    def build_statusbar(self):
        sb = QStatusBar()
        self.lbl_pos = QLabel("   ")
        self.lbl_sel = QLabel("")
        self.lbl_size = QLabel("")
        sb.addWidget(self.lbl_pos)
        sb.addWidget(self.lbl_sel)
        sb.addWidget(QWidget(), 1)
        sb.addPermanentWidget(self.lbl_size)

        self.zoom_label = QLabel("100%")
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setFixedWidth(120)
        self.zoom_slider.setRange(0, 100)
        self.zoom_slider.setValue(self._zoom_to_slider(1.0))
        self.zoom_slider.valueChanged.connect(self.on_zoom_slider)
        b_minus = QToolButton(); b_minus.setText("−"); b_minus.setAutoRaise(True)
        b_minus.clicked.connect(self.zoom_out)
        b_plus = QToolButton(); b_plus.setText("+"); b_plus.setAutoRaise(True)
        b_plus.clicked.connect(self.zoom_in)
        sb.addPermanentWidget(self.zoom_label)
        sb.addPermanentWidget(b_minus)
        sb.addPermanentWidget(self.zoom_slider)
        sb.addPermanentWidget(b_plus)
        self.setStatusBar(sb)

    def _zoom_to_slider(self, z):
        # 0..100 -> 0.1x..8x логарифмически, 100% посередине
        return int((math.log(z) - math.log(0.1)) /
                   (math.log(8.0) - math.log(0.1)) * 100)

    def _slider_to_zoom(self, v):
        return math.exp(math.log(0.1) + v / 100 *
                        (math.log(8.0) - math.log(0.1)))

    def on_zoom_slider(self, v):
        z = self._slider_to_zoom(v)
        self.canvas.set_zoom(z)

    def update_zoom_label(self):
        self.zoom_label.setText("%d%%" % round(self.canvas.zoom * 100))
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(self._zoom_to_slider(self.canvas.zoom))
        self.zoom_slider.blockSignals(False)

    def update_status_pos(self, pt):
        self.lbl_pos.setText("  %d, %d пикс" % (pt.x(), pt.y()))

    def update_status_sel(self, size):
        if size is None:
            self.lbl_sel.setText("")
        else:
            self.lbl_sel.setText("  %d × %d пикс" % (size.width(), size.height()))

    def update_status_size(self):
        self.lbl_size.setText("  %d × %d пикс  " %
                              (self.canvas.image.width(), self.canvas.image.height()))

    # -- горячие клавиши --------------------------------------------------
    def build_shortcuts(self):
        import sys
        menubar = self.menuBar()
        if sys.platform != 'darwin':
            menubar.hide()  # Прячем на Windows/Linux, чтобы не портить Ribbon
            
        edit_menu = menubar.addMenu("Правка")
        file_menu = menubar.addMenu("Файл")
        view_menu = menubar.addMenu("Вид")

        def act(menu, seq, slot, name=""):
            a = QAction(name, self)
            a.setShortcut(seq)
            a.setShortcutContext(Qt.ApplicationShortcut)
            a.triggered.connect(slot)
            menu.addAction(a)
            self.addAction(a)
            return a
            
        act(file_menu, QKeySequence.New, self.new_file, "Новый")
        act(file_menu, QKeySequence.Open, self.open_file, "Открыть")
        act(file_menu, QKeySequence.Save, self.save, "Сохранить")
        act(file_menu, QKeySequence("Ctrl+Shift+S"), self.save_as, "Сохранить как")
        act(file_menu, QKeySequence.Print, self.print_image, "Печать")
        
        act(edit_menu, QKeySequence.Undo, self.canvas.undo, "Отменить")
        
        redo_std = QKeySequence(QKeySequence.Redo)
        act(edit_menu, redo_std, self.canvas.redo, "Повторить")
        for extra in ("Ctrl+Y", "Ctrl+Shift+Z"):
            if QKeySequence(extra) != redo_std:
                act(edit_menu, QKeySequence(extra), self.canvas.redo, "Повторить")
                
        act(edit_menu, QKeySequence.Copy, self.canvas.copy_selection, "Копировать")
        act(edit_menu, QKeySequence.Cut, self.canvas.cut_selection, "Вырезать")
        act(edit_menu, QKeySequence.Paste, self.canvas.paste, "Вставить")
        act(edit_menu, QKeySequence.SelectAll, self.canvas.select_all, "Выделить всё")
        act(edit_menu, QKeySequence.Delete, self.canvas.delete_selection, "Удалить")
        
        act(view_menu, QKeySequence.ZoomIn, self.zoom_in, "Увеличить")
        act(view_menu, QKeySequence("Ctrl+="), self.zoom_in, "Увеличить (+)")
        act(view_menu, QKeySequence.ZoomOut, self.zoom_out, "Уменьшить")
        act(view_menu, QKeySequence("Escape"), self.on_escape, "Сброс")

    def on_escape(self):
        if self.canvas.text_edit is not None:
            self.canvas.cancel_text()
        elif self.canvas.curve_stage != 0:
            self.canvas.reset_curve()
            self.canvas.update()
        else:
            self.canvas.clear_selection()

    # -- стиль ------------------------------------------------------------
    def apply_style(self):
        self.setStyleSheet("""
        QMainWindow { background:#f5f6f8; }
        QTabWidget::pane { border-top:1px solid #d0d3d8; background:#fbfbfc; }
        QTabBar::tab {
            background:transparent; padding:5px 20px; margin-right:1px;
            color:#333; font-size:13px; border:1px solid transparent;
            border-top-left-radius:3px; border-top-right-radius:3px;
            min-width: 65px;
        }
        QTabBar::tab:selected { background:#fbfbfc; border:1px solid #d0d3d8;
            border-bottom:1px solid #fbfbfc; }
        QTabBar::tab:hover:!selected { background:#eef1f6; }
        QTabBar::tab:first {
            background:#2b579a; color:white; margin-right:6px;
            border-top-left-radius:0; border-top-right-radius:0;
        }
        QTabBar::tab:first:hover { background:#1f4380; }
        QToolButton { border:1px solid transparent; border-radius:3px; padding:1px;
            font-size:11px; color:#333; }
        QToolButton:hover { background:#dceafc; border:1px solid #aacbf2; }
        QToolButton:checked { background:#cfe3fb; border:1px solid #7fb0ec; }
        QToolButton:pressed { background:#bcd8f7; }
        QStatusBar { background:#f0f0f0; border-top:1px solid #d8d8d8; }
        QStatusBar QLabel { color:#444; font-size:12px; }
        QGroupBox { font-size:12px; margin-top:6px; }
        QGroupBox::title { subcontrol-origin: margin; left:8px; }
        """)

    # ===================================================================
    #  Действия инструментов
    # ===================================================================
    def set_tool(self, tool, silent=False):
        self.canvas.commit_text()
        self.canvas.commit_selection()
        self.canvas.reset_curve()
        self.canvas.tool = tool
        cursors = {
            "brush": Qt.CrossCursor, "pencil": Qt.CrossCursor,
            "eraser": Qt.CrossCursor, "fill": Qt.PointingHandCursor,
            "picker": Qt.UpArrowCursor, "magnifier": Qt.PointingHandCursor,
            "text": Qt.IBeamCursor, "shape": Qt.CrossCursor,
            "select": Qt.CrossCursor,
        }
        self.canvas.setCursor(cursors.get(tool, Qt.ArrowCursor))
        if not silent:
            self.sync_tool_buttons()

    def set_shape(self, name, silent=False):
        self.canvas.shape = name
        self.canvas.reset_curve()
        self.canvas.tool = "shape"
        self.canvas.setCursor(Qt.CrossCursor)
        for n, b in self.shape_buttons.items():
            b.setChecked(n == name)
        if not silent:
            self.sync_tool_buttons(active="shape")

    def sync_tool_buttons(self, active=None):
        tool = self.canvas.tool
        for key, btn in self.tool_buttons.items():
            if btn.isCheckable():
                btn.setChecked(key == tool)
        if tool != "shape":
            for b in self.shape_buttons.values():
                b.setChecked(False)
        else:
            for n, b in self.shape_buttons.items():
                b.setChecked(n == self.canvas.shape)

    def set_brush(self, key):
        self.canvas.brush = key
        self.set_tool("brush")

    def set_pen_width(self, w):
        self.canvas.pen_width = w
        self._update_size_button(w)

    def _update_size_button(self, w):
        pm = QPixmap(40, 30)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(Qt.black); pen.setWidthF(w); pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawLine(6, 15, 34, 15)
        p.end()
        self.btn_size.setIcon(QIcon(pm))
        self.btn_size.setIconSize(QSize(40, 30))

    def set_outline(self, style):
        self.canvas.outline_style = style

    def set_fill(self, style):
        self.canvas.fill_style = style

    def set_color1(self, color):
        self.canvas.color1 = QColor(color)
        self._paint_swatch(self.btn_color1[0], self.canvas.color1)

    def set_color2(self, color):
        self.canvas.color2 = QColor(color)
        self._paint_swatch(self.btn_color2[0], self.canvas.color2)

    def pick_color(self, initial):
        """Выбор цвета: используем нативный диалог, если возможно, для лучшей интеграции."""
        dlg = QColorDialog(QColor(initial), self)
        import platform
        if platform.system() != 'Darwin':
            dlg.setOption(QColorDialog.DontUseNativeDialog, True)
        dlg.setWindowTitle("Изменение цветов")
        dlg.setWindowModality(Qt.ApplicationModal)
        if dlg.exec_() == QDialog.Accepted:
            return dlg.currentColor()
        return QColor()

    def edit_colors(self):
        c = self.pick_color(self.canvas.color1)
        if c.isValid():
            self.set_color1(c)
            self._add_custom_color(c)

    def edit_color2(self):
        c = self.pick_color(self.canvas.color2)
        if c.isValid():
            self.set_color2(c)
            self._add_custom_color(c)

    def _add_custom_color(self, c):
        for btn in self.custom_swatches:
            if btn._color == QColor(Qt.white):
                btn._color = QColor(c)
                self._paint_palette(btn, btn._color)
                return
        # сдвигаем
        btn = self.custom_swatches[0]
        btn._color = QColor(c)
        self._paint_palette(btn, btn._color)

    # ===================================================================
    #  Масштаб
    # ===================================================================
    def zoom_in(self):
        self.canvas.set_zoom(self.canvas.zoom * 1.25)

    def zoom_out(self):
        self.canvas.set_zoom(self.canvas.zoom / 1.25)

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    # ===================================================================
    #  Изображение
    # ===================================================================
    def open_resize(self):
        dlg = ResizeDialog(self.canvas.image.width(),
                           self.canvas.image.height(), self)
        if dlg.exec_() == QDialog.Accepted:
            self.canvas.resize_image(dlg.result_w, dlg.result_h)
            self.mark_dirty()

    # ===================================================================
    #  Файл
    # ===================================================================
    OPEN_FILTER = ("Все изображения (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff "
                   "*.webp *.ico);;PNG (*.png);;JPEG (*.jpg *.jpeg);;"
                   "Точечный рисунок (*.bmp);;GIF (*.gif);;TIFF (*.tif *.tiff);;"
                   "WebP (*.webp);;Все файлы (*)")
    SAVE_FILTER = ("PNG (*.png);;JPEG (*.jpg *.jpeg);;Точечный рисунок (*.bmp);;"
                   "TIFF (*.tif *.tiff);;WebP (*.webp);;Значок (*.ico)")

    def new_file(self):
        if not self.confirm_discard():
            return
        self.canvas.new_image()
        self.file_path = None
        self.dirty = False
        self.update_title()

    def open_file(self, path=None):
        if not self.confirm_discard():
            return
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                self, "Открыть", os.path.expanduser("~"), self.OPEN_FILTER)
        if not path:
            return
        img = QImage(path)
        if img.isNull():
            QMessageBox.warning(self, "Paint", "Не удалось открыть файл.")
            return
        self.canvas.load_image(img)
        self.file_path = path
        self.dirty = False
        self.update_title()

    def save(self):
        if self.file_path:
            self._save_to(self.file_path)
        else:
            self.save_as()

    def save_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить как",
            self.file_path or os.path.join(os.path.expanduser("~"), "Безымянный.png"),
            self.SAVE_FILTER)
        if not path:
            return
        if "." not in os.path.basename(path):
            path += ".png"
        self._save_to(path)

    def _save_to(self, path):
        self.canvas.commit_text()
        self.canvas.commit_selection()
        img = self.canvas.image
        ext = os.path.splitext(path)[1].lower()

        # если формат не умеет записываться (например GIF) — мягко переходим на PNG
        from PyQt5.QtGui import QImageWriter
        writable = {bytes(f).decode().lower()
                    for f in QImageWriter.supportedImageFormats()}
        if ext.lstrip(".") not in writable:
            r = QMessageBox.question(
                self, "Paint",
                "Этот формат (%s) нельзя сохранить.\n"
                "Сохранить рисунок в формате PNG?" % ext,
                QMessageBox.Yes | QMessageBox.No)
            if r != QMessageBox.Yes:
                return
            path = os.path.splitext(path)[0] + ".png"
            ext = ".png"
        if ext in (".jpg", ".jpeg", ".bmp"):
            # эти форматы без прозрачности — кладём на белый фон
            out = QImage(img.size(), QImage.Format_RGB32)
            out.fill(Qt.white)
            p = QPainter(out); p.drawImage(0, 0, img); p.end()
            img = out
        ok = img.save(path)
        if not ok:
            QMessageBox.warning(self, "Paint", "Не удалось сохранить файл.")
            return
        self.file_path = path
        self.dirty = False
        self.update_title()

    def print_image(self):
        from PyQt5.QtPrintSupport import QPrinter, QPrintDialog
        printer = QPrinter(QPrinter.HighResolution)
        dlg = QPrintDialog(printer, self)
        if dlg.exec_() == QDialog.Accepted:
            p = QPainter(printer)
            rect = p.viewport()
            img = self.canvas.image
            size = img.size()
            size.scale(rect.size(), Qt.KeepAspectRatio)
            p.setViewport(rect.x(), rect.y(), size.width(), size.height())
            p.setWindow(img.rect())
            p.drawImage(0, 0, img)
            p.end()

    # ===================================================================
    #  Прочее
    # ===================================================================
    def mark_dirty(self):
        if not self.dirty:
            self.dirty = True
            self.update_title()

    def update_title(self):
        name = os.path.basename(self.file_path) if self.file_path else "Безымянный"
        star = "*" if self.dirty else ""
        self.setWindowTitle("%s%s — Paint" % (star, name))

    def update_actions(self):
        self.act_undo_q.setEnabled(bool(self.canvas.undo_stack))
        self.act_redo_q.setEnabled(bool(self.canvas.redo_stack))

    def update_zoom_label_safe(self):
        self.update_zoom_label()

    def confirm_discard(self):
        if not self.dirty:
            return True
        r = QMessageBox.question(
            self, "Paint",
            "Сохранить изменения в «%s»?" %
            (os.path.basename(self.file_path) if self.file_path else "Безымянный"),
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            self.save()
            return not self.dirty
        if r == QMessageBox.Cancel:
            return False
        return True

    def closeEvent(self, ev):
        if self.confirm_discard():
            ev.accept()
        else:
            ev.ignore()


def main():
    import platform
    # Корректная работа при дробном масштабе экрана (например 150%)
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    except Exception:
        pass
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    
    # Принудительно устанавливаем светлую тему (Light Mode),
    # чтобы избежать конфликтов с темной темой ОС
    from PyQt5.QtGui import QPalette, QColor
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(245, 246, 248))
    palette.setColor(QPalette.WindowText, Qt.black)
    palette.setColor(QPalette.Base, Qt.white)
    palette.setColor(QPalette.AlternateBase, QColor(245, 246, 248))
    palette.setColor(QPalette.ToolTipBase, Qt.white)
    palette.setColor(QPalette.ToolTipText, Qt.black)
    palette.setColor(QPalette.Text, Qt.black)
    palette.setColor(QPalette.Button, QColor(245, 246, 248))
    palette.setColor(QPalette.ButtonText, Qt.black)
    palette.setColor(QPalette.BrightText, Qt.red)
    palette.setColor(QPalette.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.HighlightedText, Qt.white)
    app.setPalette(palette)

    app.setApplicationName("Paint")
    app.setApplicationDisplayName("Paint")
    # связываем окно с ярлыком winpaint.desktop, чтобы GNOME показывал
    # нашу иконку (а не шестерёнку) в панели задач и Alt+Tab
    if platform.system() == 'Linux':
        app.setDesktopFileName("winpaint")
    app.setWindowIcon(icons.app_icon())
    win = PaintWindow()

    # Стартовый размер на случай, если окно потом свернут из полноэкранного,
    # и всегда открываемся развёрнуто на весь экран.
    screen = app.primaryScreen().availableGeometry()
    win.resize(min(1100, screen.width() - 80), min(680, screen.height() - 80))

    if platform.system() == 'Darwin':
        # macOS: обычное окно по центру экрана (более привычно для Mac)
        win.resize(min(1200, screen.width() - 80), min(750, screen.height() - 80))
        win.showNormal()
        win.move(
            (screen.width() - win.width()) // 2 + screen.x(),
            (screen.height() - win.height()) // 2 + screen.y()
        )
    else:
        win.showMaximized()

    # открыть файл, переданный аргументом (для интеграции с Ubuntu)
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args and os.path.isfile(args[0]):
        win.open_file(args[0])
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
