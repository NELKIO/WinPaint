"""Exercise the drawing controller against actual browser canvas pixels."""
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


class DrawingTests(unittest.TestCase):
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
        self.page = self.browser.new_page()
        self.addCleanup(self.page.close)
        self.page.goto(self.url)
        self.page.evaluate('''async () => {
            const {createDrawing} = await import('./drawing.js');
            const canvas = document.createElement('canvas'); canvas.width=100; canvas.height=100;
            const ctx = canvas.getContext('2d', {willReadFrequently:true});
            const clear = () => {ctx.fillStyle='#fff'; ctx.fillRect(0,0,100,100)};
            const pixel = (x,y) => [...ctx.getImageData(x,y,1,1).data].slice(0,3);
            const snap = () => ctx.getImageData(0,0,100,100);
            clear();
            const state = {tool:'shape',shape:'line',brush:'round',width:3,zoom:1,
                           color1:'#ff0000',color2:'#0000ff',outline:'solid',fill:'none'};
            let pending=null; const undo=[];
            const app={canvas,ctx,state,set:(k,v)=>state[k]=v,
                begin(){if(pending) throw Error('nested transaction'); pending=snap()},
                commit(){if(!pending) throw Error('missing begin'); undo.push(pending); pending=null},
                abort(){ctx.putImageData(pending,0,0); pending=null},
                change(fn){this.begin(); fn(); this.commit()}};
            const draw=createDrawing(app);
            const event = (type,x,y,button=0,shiftKey=false) =>
                draw[type]({x,y},new PointerEvent('pointer'+type,{button,shiftKey}));
            const drag = (x,y,u,v,button=0,shift=false) => {
                event('down',x,y,button,shift); event('move',u,v,button,shift); event('up',u,v,button,shift)
            };
            Object.assign(window,{draw,state,ctx,pixel,snap,clear,eventAt:event,drag,undos:undo});
        }''')

    def test_curve_two_stages_share_one_undo_and_replace_chord(self):
        self.assertEqual(self.page.evaluate('''() => {
            state.shape='curve'; drag(10,50,90,50); const chord=pixel(50,50), n=undos.length;
            drag(50,8,50,10); return [chord,n,pixel(50,50),pixel(50,30),undos.length]
        }'''), [[255,0,0], 0, [255,255,255], [255,0,0], 1])

    def test_finish_discards_incomplete_curve_and_cancel_restores_live_stroke(self):
        self.assertEqual(self.page.evaluate('''() => {
            state.shape='curve'; drag(10,50,90,50); draw.finish();
            state.tool='brush'; eventAt('down',50,50); eventAt('move',70,50); draw.cancel();
            return [pixel(50,50),undos.length]
        }'''), [[255,255,255], 0])

    def test_shift_preview_replaced_and_right_click_exchanges_shape_colors(self):
        self.assertEqual(self.page.evaluate('''() => {
            state.shape='rect'; state.fill='solid'; eventAt('down',10,10,2);
            eventAt('move',90,90,2); eventAt('up',40,20,2,true);
            return [pixel(20,35),pixel(10,25),pixel(75,75),undos.length]
        }'''), [[255,0,0], [0,0,255], [255,255,255], 1])
        self.assertEqual(self.page.evaluate('''() => {
            clear(); state.shape='line'; state.width=1; drag(10,10,44,18,0,true);
            return [pixel(43,10),pixel(40,17)]
        }'''), [[255,0,0], [255,255,255]])

    def test_fill_only_includes_same_color_pen_both_none_invisible(self):
        self.assertEqual(self.page.evaluate('''() => {
            state.outline='none'; state.fill='solid'; state.width=5; drag(20,20,80,20);
            state.fill='none'; drag(20,40,80,40); return [pixel(50,21),pixel(50,40)]
        }'''), [[0,0,255], [255,255,255]])

    def test_each_closed_shape_has_distinct_crisp_silhouette(self):
        shapes = ('oval rect rrect triangle rtriangle diamond pentagon hexagon arrow_r arrow_l '
                  'arrow_u arrow_d star4 star5 star6 callout_round callout_rect callout_cloud heart lightning').split()
        seen = set()
        for shape in shapes:
            with self.subTest(shape=shape):
                image, colors = self.page.evaluate('''shape => {
                    clear(); state.shape=shape; state.fill='solid'; drag(80,80,20,20);
                    const data=snap().data, colors=new Set();
                    for(let i=0;i<data.length;i+=4) colors.add(data.slice(i,i+3).join(','));
                    return [ctx.canvas.toDataURL(),Array.from(colors).sort()]
                }''', shape)
                self.assertEqual(colors, ['0,0,255','255,0,0','255,255,255'])
                self.assertNotIn(image, seen)
                seen.add(image)

    def test_pencil_crisp_eraser_square_and_uses_secondary_for_both_buttons(self):
        self.assertEqual(self.page.evaluate('''() => {
            state.tool='pencil'; drag(5,5,60,20,2);
            const data=snap().data; let antialias=false;
            for(let i=0;i<data.length;i+=4) if(data[i]!==255 && data[i]!==0) antialias=true;
            const pencil=pixel(60,20); state.tool='eraser'; state.width=2;
            drag(50,50,50,50,2); return [antialias,pencil,pixel(47,47),pixel(45,50)]
        }'''), [False, [0,0,255], [0,0,255], [255,255,255]])

    def test_brush_width_caps_and_translucency(self):
        for brush, green in [('round',0), ('calligraphy1',0), ('calligraphy2',0), ('oil',95),
                             ('crayon',145), ('marker',135), ('watercolor',185)]:
            with self.subTest(brush=brush):
                center, extension = self.page.evaluate('''brush => {
                    clear(); Object.assign(state,{tool:'brush',brush,width:5}); drag(25,50,75,50);
                    return [pixel(50,50),pixel(78,50)]
                }''', brush)
                self.assertLessEqual(abs(center[1]-green), 1)
                self.assertEqual(extension == [255,255,255], brush == 'calligraphy1')
        sprayed = self.page.evaluate('''() => {
            clear(); state.brush='airbrush'; state.width=12; drag(50,50,50,50);
            return snap().data.filter((v,i)=>i%4===1 && v<250).length
        }''')
        self.assertGreater(sprayed, 1)
        self.assertLess(sprayed, 100)  # Spray droplets, not a solid 24-pixel disk.

    def test_fill_four_connected_rgba_picker_and_zoom_without_image_history(self):
        self.assertEqual(self.page.evaluate('''() => {
            ctx.fillStyle='#000'; ctx.fillRect(0,0,60,60);
            ctx.fillRect(60,60,40,40); ctx.clearRect(20,20,5,5);
            state.tool='fill'; drag(1,1,1,1,2);
            state.tool='picker'; drag(5,5,5,5);
            drag(61,61,61,61,2); state.tool='magnifier'; drag(3,3,3,3);
            const z=state.zoom; drag(3,3,3,3,2);
            return [pixel(59,59),pixel(60,60),ctx.getImageData(22,22,1,1).data[3],
                    state.color1,state.color2,z,state.zoom,undos.length]
        }'''), [[0,0,255], [0,0,0], 0, '#0000ff', '#000000', 1.25, 1, 1])
