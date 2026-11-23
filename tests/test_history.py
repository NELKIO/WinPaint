import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QApplication, QMessageBox
from winpaint.paint import PaintWindow


class DocumentHistory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = PaintWindow()
        self.addCleanup(self.window.deleteLater)
        self.canvas = self.window.canvas
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = str(Path(temp.name) / 'drawing.png')
        self.canvas.push_undo()
        self.canvas.image.setPixelColor(0, 0, QColor('red'))
        self.window._save_to(self.path)

    def test_undo_after_save_requires_confirmation_until_redone(self):
        self.canvas.undo()
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Cancel):
            self.assertFalse(self.window.confirm_discard())
        self.canvas.redo()
        self.assertFalse(self.window.dirty)

    def test_redo_after_saving_undone_image_is_unsaved(self):
        self.canvas.undo()
        self.window.save()
        self.canvas.redo()
        self.assertTrue(self.window.dirty)

    def test_undo_cancels_unfinished_curve_preview(self):
        from PyQt5.QtCore import QPoint
        self.canvas.handle_curve_press(QPoint(20, 20))
        self.canvas.handle_curve_release(QPoint(120, 20))
        self.canvas.undo()
        self.assertIsNone(self.canvas.temp_image)
        self.assertEqual(self.canvas.curve_stage, 0)
        self.assertFalse(self.window.dirty)

    def test_curve_finished_after_save_is_unsaved(self):
        from PyQt5.QtCore import QPoint
        self.canvas.handle_curve_press(QPoint(20, 20))
        self.canvas.handle_curve_release(QPoint(120, 20))
        self.window.save()
        self.canvas.handle_curve_press(QPoint(60, 80))
        self.canvas.handle_curve_release(QPoint(60, 80))
        self.assertTrue(self.window.dirty)

    def test_new_document_disables_undo(self):
        self.window.new_file()
        self.assertFalse(self.window.act_undo_q.isEnabled())

    def test_open_document_disables_redo(self):
        self.canvas.undo()
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Discard):
            self.window.open_file(self.path)
        self.assertFalse(self.window.act_redo_q.isEnabled())
