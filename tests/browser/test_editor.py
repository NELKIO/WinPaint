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
        self.page = self.browser.new_page(viewport={'width': 1280, 'height': 800})
        self.addCleanup(self.page.close)
        self.errors = []
        self.page.on('pageerror', lambda err: self.errors.append(str(err)))
        self.assertEqual(self.page.goto(self.url).status, 200)
        self.canvas = self.page.locator('#canvas')
        self.assertEqual(self.canvas.count(), 1)
        self.page.set_default_timeout(5000)

    def tearDown(self):
        self.assertEqual(self.errors, [])

    def pixel(self, x=80, y=80):
        return self.canvas.evaluate('(c,[x,y]) => [...c.getContext("2d").getImageData(x,y,1,1).data]', [x,y])

    def stroke(self, y=80):
        # On a narrow screen scrolling the *whole* canvas into view centers it
        # in Firefox, putting these top-left sample points outside the viewport.
        b = self.canvas.bounding_box()
        w,h = self.canvas.evaluate('c=>[c.width,c.height]')
        pos = lambda x: (b['x']+x*b['width']/w, b['y']+y*b['height']/h)
        m = self.page.mouse
        m.move(*pos(50)); m.down(); m.move(*pos(110), steps=5); m.up()

    def test_scaled_brush_history_eraser_and_branch(self):
        self.assertTrue(self.page.get_by_role('button', name='Отменить').is_disabled())
        self.page.locator('#color1').fill('#cc2244')
        self.page.locator('[data-tool=pencil]').click()
        self.stroke()
        red = [204,34,68,255]; white = [255]*4
        self.assertEqual(self.pixel(), red)
        self.assertEqual(self.pixel(y=87), white)
        self.assertEqual(self.pixel(y=94), white)
        self.page.get_by_role('button', name='Отменить').click()
        self.assertEqual(self.pixel(), white)
        self.page.locator('#redo').click()
        self.assertEqual(self.pixel(), red)
        self.page.get_by_role('button', name='Ластик').click(); self.stroke()
        self.assertEqual(self.pixel(), white)
        self.page.get_by_role('button', name='Отменить').click()
        self.assertEqual(self.pixel(), red)
        self.stroke(100)
        self.assertTrue(self.page.locator('#redo').is_disabled())

    def test_png_download_roundtrip_and_import_reset(self):
        self.stroke()
        drawn = self.pixel()
        self.assertNotEqual(drawn, [255]*4)
        with self.page.expect_download() as pending:
            self.page.locator('#save').click()
            self.page.get_by_role('dialog').get_by_role('button', name='Сохранить', exact=True).click()
        png = pending.value.path().read_bytes()
        self.assertEqual(png[:8], b'\x89PNG\r\n\x1a\n')
        self.page.get_by_role('button', name='Отменить').click()
        self.page.locator('input[type=file]').set_input_files({'name':'drawing.png','mimeType':'image/png','buffer':png})
        self.page.get_by_role('button', name='Не сохранять').click()
        self.page.wait_for_function("document.querySelector('[role=status]').textContent.includes('drawing.png')")
        self.assertEqual(self.pixel(), drawn)
        self.assertTrue(self.page.locator('#redo').is_disabled())
        self.assertTrue(self.page.get_by_role('button', name='Отменить').is_disabled())

    def test_invalid_png_preserves_document_and_history(self):
        self.stroke(); drawn = self.pixel()
        for name, data in [('broken.png', b'bad'), ('large.png', b'\x89PNG\r\n\x1a\n'+struct.pack('>I4sII',13,b'IHDR',65535,65535))]:
            self.page.locator('input[type=file]').set_input_files({'name':name,'mimeType':'image/png','buffer':data})
            self.page.wait_for_function("name=>document.querySelector('[role=status]').textContent.includes(name)", arg=name)
            self.assertEqual(self.pixel(), drawn)
            self.assertTrue(self.page.get_by_role('button', name='Отменить').is_enabled())

    def test_new_prompts_before_discard(self):
        self.stroke(); drawn = self.pixel()
        self.page.keyboard.press('Control+n')
        self.page.get_by_role('dialog').get_by_role('button', name='Отмена').click()
        self.assertEqual(self.pixel(), drawn)
        self.page.keyboard.press('Control+n')
        self.page.get_by_role('button', name='Не сохранять').click()
        self.page.wait_for_function("document.title === 'Безымянный — Paint'")
        self.assertEqual(self.pixel(), [255]*4)
        self.assertTrue(self.page.locator('#undo').is_disabled())

    def test_resize_handles_keep_pixels_and_undo_dimensions(self):
        self.stroke(); drawn = self.pixel()
        handle = self.page.locator('#handle-se').bounding_box()
        x, y = handle['x']+2, handle['y']+2
        self.page.mouse.move(x,y); self.page.mouse.down(); self.page.mouse.move(x+20,y+10); self.page.mouse.up()
        self.assertEqual(self.canvas.evaluate('c=>[c.width,c.height]'), [980,550])
        self.assertEqual(self.pixel(), drawn)
        self.page.locator('#undo').click()
        self.assertEqual(self.canvas.evaluate('c=>[c.width,c.height]'), [960,540])

    def test_rotate_flip_resize_and_undo(self):
        self.stroke(); color = self.pixel()
        self.page.locator('[data-menu=rotate]').click()
        self.page.get_by_role('menuitem', name='Повернуть на 90° по часовой').click()
        self.assertEqual(self.canvas.evaluate('c=>[c.width,c.height]'), [540,960])
        self.assertEqual(self.pixel(459,80), color)
        self.page.locator('[data-menu=rotate]').click()
        self.page.get_by_role('menuitem', name='Отразить по горизонтали').click()
        self.assertEqual(self.pixel(80,80), color)
        self.page.locator('[data-command=resize]').click()
        dlg = self.page.get_by_role('dialog'); dlg.get_by_label('По горизонтали:').fill('50')
        self.assertEqual(dlg.get_by_label('По вертикали:').input_value(), '50')
        dlg.get_by_role('button', name='ОК', exact=True).click()
        self.page.wait_for_function("document.querySelector('#canvas').width === 270")
        self.assertLess(self.pixel(40,40)[0], 190)  # filtered 3px stroke at half scale
        self.assertEqual(self.pixel(50,40), [255]*4)
        self.page.locator('#undo').click(); self.assertEqual(self.pixel(80,80), color)
        self.assertEqual(self.canvas.evaluate('c=>[c.width,c.height]'), [540,960])

    def test_undo_half_finished_curve_does_not_revert_previous_stroke(self):
        self.stroke(); color = self.pixel()
        self.page.locator('[data-shape=curve]').click(); self.stroke(130)
        self.page.locator('#undo').click()
        self.assertEqual(self.pixel(), color)
        self.assertEqual(self.pixel(y=130), [255]*4)
        self.page.locator('#undo').click(); self.assertEqual(self.pixel(), [255]*4)

    def test_ribbon_shape_select_crop_and_text_stamp(self):
        page = self.page
        def drag(x1,y1,x2,y2):
            b = self.canvas.bounding_box(); m = page.mouse
            m.move(b['x']+x1,b['y']+y1); m.down(); m.move(b['x']+x2,b['y']+y2,steps=4); m.up()
        page.locator('[data-shape=rect]').click()
        page.locator('[data-menu=fill]').click()
        page.get_by_role('menuitemradio', name='Сплошной цвет').click()
        page.locator('[data-color="#ed1c24"]').click(button='right')
        drag(15,15,100,60)
        self.assertEqual(self.pixel(48,36), [237,28,36,255])
        page.locator('[data-tool=select]').click(); drag(40,29,65,48)
        page.locator('[data-command=crop]').click()
        self.assertEqual(self.canvas.evaluate('c=>[c.width,c.height]'), [26,20])
        self.assertEqual(self.pixel(1,1), [237,28,36,255])
        page.locator('#undo').click()
        page.locator('[data-tool=text]').click()
        self.canvas.click(position={'x':140,'y':100}); field=page.get_by_role('textbox',name='Текст',exact=True)
        field.fill('Paint'); page.locator('[data-tool=pencil]').click()
        self.assertTrue(self.canvas.evaluate('c=>c.getContext("2d").getImageData(140,100,90,40).data.some((v,i)=>i%4===0 && v<200)'))
        page.locator('#undo').click()
        self.assertTrue(self.canvas.evaluate('c=>c.getContext("2d").getImageData(140,100,90,40).data.every(v=>v===255)'))

    def test_print_view_excludes_chrome_and_grid(self):
        self.page.get_by_role('tab', name='Вид').click()
        self.page.get_by_label('Линии сетки').check()
        self.assertEqual(self.page.locator('#zoom-value').inner_text(),'400%')
        self.page.emulate_media(media='print')
        self.assertTrue(self.canvas.is_visible())
        self.assertFalse(self.page.locator('#ribbon').is_visible())
        self.assertFalse(self.page.locator('.pixel-grid').is_visible())

    def test_oriented_png_import(self):
        import zlib
        def chunk(kind, data):
            return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
        exif = bytes.fromhex('49492a0008000000010012010300010000000600000000000000')
        png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 80,60,8,2,0,0,0)) +
               chunk(b'eXIf', exif) + chunk(b'IDAT', zlib.compress((b'\0' + bytes([24,68,12])*80)*60)) + chunk(b'IEND', b''))
        self.page.locator('input[type=file]').set_input_files({'name':'rotated.png','mimeType':'image/png','buffer':png})
        self.page.wait_for_function("document.querySelector('[role=status]').textContent.includes('rotated.png')")
        self.assertEqual(self.pixel(20,20), [24,68,12,255])

    def test_narrow_layout_and_scrollable_workspace(self):
        self.page.set_viewport_size({'width': 360, 'height': 720})
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        self.page.locator('#workspace').evaluate('el=>{el.scrollLeft=0;el.scrollTop=0}')
        self.assertGreater(self.page.locator('#workspace').evaluate('el=>el.scrollWidth'),360)
        self.stroke(); self.assertNotEqual(self.pixel(), [255]*4)
