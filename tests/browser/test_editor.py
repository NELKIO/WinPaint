"""Run with python -m unittest discover -s tests/browser (optional EDITOR_URL)."""
import functools
import os
import struct
import tempfile
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class BrowserEditor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.environ.get('EDITOR_URL')
        if not cls.url:
            root = tempfile.TemporaryDirectory()
            cls.addClassCleanup(root.cleanup)
            (Path(root.name) / 'WinPaint').symlink_to(Path(__file__).resolve().parents[2] / 'web', target_is_directory=True)
            server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=root.name))
            cls.addClassCleanup(server.server_close)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            cls.addClassCleanup(server.shutdown)
            cls.url = f'http://127.0.0.1:{server.server_port}/WinPaint/'
        pw = sync_playwright().start()
        cls.addClassCleanup(pw.stop)
        cls.browser = getattr(pw, os.getenv('TEST_BROWSER', 'chromium')).launch()
        cls.addClassCleanup(cls.browser.close)

    def setUp(self):
        self.page = self.browser.new_page(viewport={'width': 800, 'height': 700})
        self.addCleanup(self.page.close)
        self.errors = []
        self.page.on('pageerror', lambda err: self.errors.append(str(err)))
        self.assertEqual(self.page.goto(self.url).status, 200)
        self.canvas = self.page.locator('canvas')
        self.assertEqual(self.canvas.count(), 1)
        self.page.set_default_timeout(5000)

    def tearDown(self):
        self.assertEqual(self.errors, [])

    def pixel(self, x=80, y=80):
        return self.canvas.evaluate('(c,[x,y]) => [...c.getContext("2d").getImageData(x,y,1,1).data]', [x,y])

    def stroke(self, y=80):
        self.canvas.scroll_into_view_if_needed()
        b = self.canvas.bounding_box()
        w,h = self.canvas.evaluate('c=>[c.width,c.height]')
        pos = lambda x: (b['x']+x*b['width']/w, b['y']+y*b['height']/h)
        m = self.page.mouse
        m.move(*pos(50)); m.down(); m.move(*pos(110), steps=5); m.up()

    def test_scaled_brush_history_eraser_and_branch(self):
        self.assertTrue(self.page.get_by_role('button', name='Отменить').is_disabled())
        self.page.get_by_label('Цвет кисти').fill('#cc2244')
        self.page.get_by_label('Толщина').fill('20')
        self.stroke()
        red = [204,34,68,255]; white = [255]*4
        self.assertEqual(self.pixel(), red)
        self.assertTrue(all(abs(a-b) <= 2 for a,b in zip(self.pixel(y=87), red)))
        self.assertEqual(self.pixel(y=94), white)
        self.page.get_by_role('button', name='Отменить').click()
        self.assertEqual(self.pixel(), white)
        self.page.get_by_role('button', name='Повторить').click()
        self.assertEqual(self.pixel(), red)
        self.page.get_by_role('button', name='Ластик').click(); self.stroke()
        self.assertEqual(self.pixel(), white)
        self.page.get_by_role('button', name='Отменить').click()
        self.assertEqual(self.pixel(), red)
        self.stroke(100)
        self.assertTrue(self.page.get_by_role('button', name='Повторить').is_disabled())

    def test_png_download_roundtrip_and_import_reset(self):
        self.stroke()
        drawn = self.pixel()
        self.assertNotEqual(drawn, [255]*4)
        with self.page.expect_download() as pending:
            self.page.get_by_role('button', name='Сохранить PNG').click()
        png = pending.value.path().read_bytes()
        self.assertEqual(png[:8], b'\x89PNG\r\n\x1a\n')
        self.page.get_by_role('button', name='Отменить').click()
        self.page.locator('input[type=file]').set_input_files({'name':'drawing.png','mimeType':'image/png','buffer':png})
        self.page.wait_for_function("document.querySelector('[role=status]').textContent.includes('drawing.png')")
        self.assertEqual(self.pixel(), drawn)
        self.assertTrue(self.page.get_by_role('button', name='Повторить').is_disabled())
        self.assertTrue(self.page.get_by_role('button', name='Отменить').is_disabled())

    def test_invalid_png_preserves_document_and_history(self):
        self.stroke(); drawn = self.pixel()
        for name, data in [('broken.png', b'bad'), ('large.png', b'\x89PNG\r\n\x1a\n'+struct.pack('>I4sII',13,b'IHDR',65535,65535))]:
            self.page.locator('input[type=file]').set_input_files({'name':name,'mimeType':'image/png','buffer':data})
            self.page.wait_for_function("name=>document.querySelector('[role=status]').textContent.includes(name)", arg=name)
            self.assertEqual(self.pixel(), drawn)
            self.assertTrue(self.page.get_by_role('button', name='Отменить').is_enabled())

    def test_narrow_layout_and_release_link(self):
        self.page.set_viewport_size({'width': 360, 'height': 720})
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        self.assertEqual(self.page.get_by_role('link',name='Скачать полную версию').get_attribute('href'), 'https://github.com/NELKIO/WinPaint/releases')
        self.stroke(); self.assertNotEqual(self.pixel(), [255]*4)
