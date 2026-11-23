"""Exercise the ribbon through its public app.set/app.run interface."""
import functools
import os
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


# Replace only the editor module: use the actual HTML, styles, ribbon and icons.
MOCK_EDITOR = '''import {initRibbon} from './ribbon.js';
const state = {tool:'pencil', brush:'round', shape:'line', width:3, outline:'solid',
 fill:'none', color1:'#000000', color2:'#ffffff', zoom:1, grid:false, showStatus:true};
window.calls=[]; window.ribbonState=state;
initRibbon({state, run:(...args)=>calls.push(args), set:(key,value)=>{
 state[key]=value; if(['brush','shape'].includes(key)) state.tool=key;
 document.dispatchEvent(new Event('paint:update'));
}});'''


class RibbonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.getenv('EDITOR_URL')
        if not cls.url:
            web = Path(__file__).resolve().parents[2] / 'web'
            server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=web))
            cls.addClassCleanup(server.server_close)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            cls.addClassCleanup(server.shutdown)
            cls.url = f'http://127.0.0.1:{server.server_port}/'
        pw = sync_playwright().start()
        cls.addClassCleanup(pw.stop)
        cls.browser = getattr(pw, os.getenv('TEST_BROWSER', 'chromium')).launch()
        cls.addClassCleanup(cls.browser.close)

    def setUp(self):
        self.p = self.browser.new_page(viewport={'width': 1280, 'height': 800})
        self.addCleanup(self.p.close)
        self.p.route('**/editor.js', lambda route: route.fulfill(content_type='text/javascript', body=MOCK_EDITOR))
        self.p.goto(self.url)
        self.p.wait_for_selector('[data-shape=line]')

    def test_home_palette_shapes_brushes_and_keyboard_file_menu(self):
        p = self.p
        self.assertEqual(p.title(), 'Безымянный — Paint')
        self.assertTrue(p.locator('#undo').is_disabled())
        p.evaluate("ribbonState.selectionPending=true; document.dispatchEvent(new Event('paint:update'))")
        self.assertTrue(p.locator('#undo').is_enabled())
        self.assertEqual(p.locator('#home h2').all_text_contents(),
                         ['Буфер обмена','Изображение','Инструменты','Кисти','Фигуры','Размер','Цвета'])
        self.assertEqual(p.locator('#tools button').count(), 6)
        self.assertEqual(p.locator('#shapes button').count(), 22)
        self.assertEqual(p.locator('#palette button').count(), 30)
        self.assertEqual(p.locator('img').evaluate_all('(imgs)=>imgs.filter(i=>!i.complete || !i.naturalWidth).length'), 0)
        p.get_by_role('button', name='Сердце').click()
        self.assertEqual(p.locator('[data-shape=heart]').get_attribute('aria-pressed'), 'true')
        p.get_by_role('button',name='Кисти').click()
        self.assertEqual(p.get_by_role('menuitemradio').count(), 8)
        p.get_by_role('menuitemradio', name='Распылитель').click()
        self.assertEqual(p.locator('[data-shape=heart]').get_attribute('aria-pressed'), 'false')
        self.assertEqual(p.locator('[data-menu=brush]').get_attribute('aria-pressed'), 'true')
        p.locator('[data-color="#22b14c"]').click(button='right')
        self.assertEqual(p.locator('#color2').input_value(), '#22b14c')
        p.locator('#file-menu').focus()
        p.keyboard.press('ArrowDown'); p.keyboard.press('ArrowDown'); p.keyboard.press('Enter')
        self.assertEqual(p.evaluate('calls.at(-1)[0]'), 'open')

    def test_narrow_menus_workspace_and_view(self):
        p = self.p
        p.set_viewport_size({'width': 320,'height': 640})
        self.assertEqual(p.locator('#canvas').bounding_box()['width'], 960)
        self.assertTrue(p.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        p.locator('[data-menu="width"]').click()
        menu = p.get_by_role('menu').bounding_box()
        self.assertGreaterEqual(menu['x'],0)
        self.assertLessEqual(menu['x']+menu['width'],320)
        p.get_by_role('menuitemradio',name='12 пикселей').click()
        self.assertEqual(p.locator('.width-sample').bounding_box()['height'],12)
        p.locator('[data-menu="rotate"]').click()
        p.get_by_role('menuitem',name='Отразить по вертикали').click()
        self.assertEqual(p.evaluate('calls.at(-1)'), ['flip','v'])
        p.get_by_role('tab',name='Вид').click(); p.get_by_label('Линии сетки').check()
        self.assertEqual(p.locator('#zoom-value').inner_text(), '400%')
        p.get_by_label('Строка состояния').uncheck()
        self.assertTrue(p.locator('#statusbar').is_hidden())
        p.get_by_label('Строка состояния').check()
        p.get_by_role('button',name='100%',exact=True).click()
        self.assertEqual(p.locator('#zoom-value').inner_text(), '100%')
        self.assertGreater(p.locator('#workspace').evaluate('el=>el.scrollWidth'),320)
