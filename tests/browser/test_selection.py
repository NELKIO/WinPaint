"""Exercise selection.js in a real browser at 150% canvas zoom."""
import functools
import os
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


# Use a small canvas with an identifiable mark and the same transaction contract
# as the application. No dependence on ribbon layout, OS clipboard contents, or
# other browser tests.
FIXTURE = '''<!doctype html><meta charset="utf-8"><div id="textbar"></div>
<div id="surface" style="position:relative;width:240px;height:150px">
<canvas width="160" height="100" style="width:100%;height:100%"></canvas></div>
<script type="module">
import {createSelection} from './selection.js';
const canvas = document.querySelector('canvas'), ctx = canvas.getContext('2d');
ctx.fillStyle='white'; ctx.fillRect(0,0,160,100); ctx.fillStyle='red'; ctx.fillRect(12,12,4,4);
const state = {tool:'select', color1:'#000000', color2:'#ffffff', zoom:1.5};
let original; window.historySteps = []; window.state = state;
const app = {canvas, ctx, state, update(){}, message(s){window.msg=s},
  set(k,v){ state[k]=v }, begin(){ if(original)throw Error('nested transaction');
    original=ctx.getImageData(0,0,canvas.width,canvas.height) },
  commit(){historySteps.push(original);original=null}, abort(){ctx.putImageData(original,0,0);original=null},
  change(fn){app.begin();fn();app.commit()},
  replaceBitmap(c){canvas.width=c.width;canvas.height=c.height;ctx.drawImage(c,0,0)} };
window.sel = createSelection(app);
for (const [event, fn] of [['pointerdown','down'],['pointermove','move'],['pointerup','up']]) {
  canvas.addEventListener(event,e=>{const b=canvas.getBoundingClientRect();
    if(fn==='down'){e.preventDefault();canvas.setPointerCapture(e.pointerId)}
    sel[fn]({x:(e.clientX-b.left)*canvas.width/b.width,y:(e.clientY-b.top)*canvas.height/b.height},e) });
}
window.px=(x,y)=>Array.from(ctx.getImageData(x,y,1,1).data);
</script>'''


class SelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[2] / 'web'
        server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=root))
        cls.addClassCleanup(server.server_close)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        cls.addClassCleanup(server.shutdown)
        cls.url = os.environ.get('EDITOR_URL') or f'http://127.0.0.1:{server.server_port}/'
        pw = sync_playwright().start()
        cls.addClassCleanup(pw.stop)
        cls.engine = os.getenv('TEST_BROWSER', 'chromium')
        cls.browser = getattr(pw, cls.engine).launch()
        cls.addClassCleanup(cls.browser.close)

    def setUp(self):
        self.page = self.browser.new_page()
        self.addCleanup(self.page.close)
        self.page.route('**/fixture.html', lambda r: r.fulfill(content_type='text/html', body=FIXTURE))
        self.page.goto(self.url.rstrip('/') + '/fixture.html')
        self.page.wait_for_function('window.sel !== undefined', timeout=2500)
        self.ev = self.page.evaluate
        self.mouse = self.page.mouse

    def pos(self, x, y):
        b = self.page.locator('#surface > canvas').bounding_box()
        return b['x'] + (x + .4)*1.5, b['y'] + (y + .4)*1.5

    def drag(self, x, y, xx, yy):
        self.mouse.move(*self.pos(x, y)); self.mouse.down()
        self.mouse.move(*self.pos(xx, yy), steps=5); self.mouse.up()

    def select_mark(self):
        self.drag(19, 19, 10, 10)

    def test_cancel_then_move_and_crop(self):
        self.select_mark(); self.drag(13,13,33,33)
        self.assertTrue(self.ev('state.selectionPending'))
        self.ev('sel.cancel()')
        self.assertFalse(self.ev('state.selectionPending'))
        self.assertEqual(self.ev('px(13,13)'), [255,0,0,255])
        self.assertEqual(self.ev('historySteps.length'), 0)
        self.select_mark(); self.drag(13,13,33,33)
        self.ev("sel.run('crop')")
        self.assertEqual(self.ev("[document.querySelector('canvas').width,document.querySelector('canvas').height]"), [10,10])
        self.assertEqual(self.ev('px(3,3)'), [255,0,0,255])
        self.assertIsNone(self.ev('state.selectionSize'))

    def test_cut_internal_paste_select_all_and_delete(self):
        self.ev("Object.defineProperty(navigator,'clipboard',{value:undefined})")
        self.select_mark(); self.ev("sel.run('cut')")
        self.assertEqual(self.ev('px(13,13)'), [255]*4)
        self.ev("sel.run('paste')"); self.drag(3,3,43,33); self.ev('sel.finish()')
        self.assertEqual(self.ev('px(43,33)'), [255,0,0,255])
        self.assertEqual(self.ev('historySteps.length'), 2)
        self.ev("sel.run('selectAll');sel.run('delete')")
        self.assertEqual(self.ev('px(43,33)'), [255]*4)

    def test_image_paste_event(self):
        self.ev('''async () => {const c=document.createElement('canvas'); c.width=c.height=5;
          c.getContext('2d').fillRect(0,0,5,5);
          const d=new DataTransfer(); d.items.add(new File([await new Promise(r=>c.toBlob(r))], 'p.png',{type:'image/png'}));
          // Firefox drops clipboardData from the synthetic event constructor.
          const e=new Event('paste',{bubbles:true,cancelable:true}); Object.defineProperty(e,'clipboardData',{value:d});
          document.dispatchEvent(e);}''')
        self.page.wait_for_function('state.selectionSize?.width===5')
        self.ev('sel.finish()'); self.assertEqual(self.ev('px(2,2)'), [0,0,0,255])

    def test_plain_text_paste_while_editing_does_not_paste_bitmap(self):
        self.ev("Object.defineProperty(navigator,'clipboard',{value:undefined}); sel.run('copy'); state.tool='text'")
        self.mouse.click(*self.pos(5,5))
        field = self.page.get_by_role('textbox', name='Текст')
        field.press_sequentially('A')
        field.evaluate('''el => {const d=new DataTransfer(); d.setData('text/plain','Б');
          d.setData('text/html','<h1>ignored</h1>'); const e=new Event('paste',{bubbles:true,cancelable:true});
          Object.defineProperty(e,'clipboardData',{value:d}); el.dispatchEvent(e)}''')
        self.assertEqual(field.inner_text(), 'AБ')
        self.assertFalse(self.ev('state.selectionPending'))
        self.page.get_by_role('button', name='Полужирный').click()
        self.assertEqual(field.evaluate("el=>getComputedStyle(el.firstElementChild).fontWeight"), '700')
        self.ev('sel.finish()')
        self.assertEqual(self.ev('historySteps.length'), 1)

    def test_system_image_clipboard(self):
        if self.engine != 'chromium':
            self.skipTest('system clipboard permission grants are browser-specific')
        self.page.context.grant_permissions(['clipboard-read', 'clipboard-write'])
        self.select_mark(); self.ev("sel.run('copy')")
        self.assertEqual(self.ev('''async()=>{const item=(await navigator.clipboard.read())[0];
          const b=await createImageBitmap(await item.getType('image/png'));return [b.width,b.height]}'''), [10,10])
        self.ev('''async()=>{const c=document.createElement('canvas'); c.width=c.height=7;
          const blob=await new Promise(r=>c.toBlob(r)); await navigator.clipboard.write([new ClipboardItem({'image/png':blob})]);}''')
        self.ev("sel.run('paste')"); self.assertEqual(self.ev('state.selectionSize.width'), 7)

    def test_rich_text_range_and_multiline_commit(self):
        self.ev("state.tool='text'"); self.mouse.click(*self.pos(4,4))
        field = self.page.get_by_role('textbox', name='Текст')
        field.press_sequentially('small'); field.press('Enter'); field.press_sequentially('BIG')
        for _ in 'BIG':
            field.press('Shift+ArrowLeft')
        self.page.get_by_role('button', name='Полужирный').click()
        self.page.get_by_role('button', name='Курсив').click()
        self.page.get_by_role('button', name='Подчёркнутый').click()
        size = self.page.get_by_label('Размер шрифта'); size.fill('30'); size.press('Enter')
        self.page.get_by_label('Шрифт', exact=True).select_option('monospace')
        self.assertEqual(self.ev('getSelection().toString()'), 'BIG')
        self.ev('sel.finish()')
        self.assertEqual(field.count(), 0)
        self.assertEqual(self.ev('historySteps.length'), 1)
        # First line remains small, second line is large and underlined.
        rows = self.ev('''()=>Array.from({length:95},(_,y)=>Array.from({length:150},(_,x)=>px(x,y)[0]<128)
          .map((v,i)=>v?i:-1).filter(i=>i>=0))''')
        self.assertTrue(any(5 < len(row) < 40 for row in rows[:22]))
        self.assertTrue(any(len(row)>48 for row in rows[23:67]))
        self.mouse.click(*self.pos(6,60)); field.fill('discard'); field.press('Escape')
        self.assertEqual(field.count(), 0); self.assertEqual(self.ev('historySteps.length'), 1)
