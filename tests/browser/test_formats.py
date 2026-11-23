"""Format module tests, independent of editor UI. Set TEST_BROWSER to select an engine."""
import base64
import functools
import os
import struct
import tempfile
import threading
import unittest
import zlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright


# Independently encoded (Pillow) animated GIF, LZW TIFF, lossless WebP and DIB ICO.
FIXTURES = {
    'gif': 'R0lGODlhBQADAIEAAO4iMwAAAAAAAAAAACH/C05FVFNDQVBFMi4wAwEAAAAh+QQAAQAAACwAAAAABQADAAAICAABCBxIsGBAACH5BAEBAAEALAAAAAAFAAMAgQAA/wAAAAAAAAAAAAgIAAEIHEiwYEAAOw==',
    'tif': 'SUkqABwAAACAO4RDOBQSBwWEQeFQaGQmGwuAgAoAAAEDAAEAAAAFAAAAAQEDAAEAAAADAAAAAgEDAAMAAACaAAAAAwEDAAEAAAAFAAAABgEDAAEAAAACAAAAEQEEAAEAAAAIAAAAFQEDAAEAAAADAAAAFgEDAAEAAAADAAAAFwEEAAEAAAAUAAAAHAEDAAEAAAABAAAAAAAAAAgACAAIAA==',
    'jpeg-compressed.tif': 'SUkqADQAAAD/2P/AABEIAAMABQNSEQBHEQBCEQD/2gAMA1IARwBCAAA/APbq8hrzKv/ZAAsAAAEDAAEAAAAFAAAAAQEDAAEAAAADAAAAAgEDAAMAAAC+AAAAAwEDAAEAAAAHAAAABgEDAAEAAAACAAAAEQEEAAEAAAAIAAAAFQEDAAEAAAADAAAAFgEDAAEAAAADAAAAFwEEAAEAAAArAAAAHAEDAAEAAAABAAAAWwEHACEBAADEAAAAAAAAAAgACAAIAP/Y/9sAQwAIBgYHBgUIBwcHCQkICgwUDQwLCwwZEhMPFB0aHx4dGhwcICQuJyAiLCMcHCg3KSwwMTQ0NB8nOT04MjwuMzQy/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/9k=',
    'webp': 'UklGRh4AAABXRUJQVlA4TBEAAAAvBIAAAAdQkbp3pv+BiOh/AAA=',
    'ico': 'AAABAAEABQMAAAAAGABkAAAAFgAAACgAAAAFAAAABgAAAAEAGAAAAAAAMAAAAMQOAADEDgAAAAAAAAAAAAAzIu4zIu4zIu4zIu4zIu4AMyLuMyLuMyLuMyLuMyLuADMi7jMi7jMi7jMi7jMi7gAAAAAAAAAAAAAAAAA=',
}


def chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class BrowserFormats(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = tempfile.TemporaryDirectory()
        cls.addClassCleanup(root.cleanup)
        (Path(root.name) / 'Paint').symlink_to(Path(__file__).resolve().parents[2] / 'web', target_is_directory=True)
        # A blank page isolates the module from the UI, under the same subpath as a Pages deployment.
        (Path(root.name) / 'blank.html').write_text('<!doctype html>')
        server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=root.name))
        cls.addClassCleanup(server.server_close)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        cls.addClassCleanup(server.shutdown)
        cls.origin = f'http://127.0.0.1:{server.server_port}'
        pw = sync_playwright().start()
        cls.addClassCleanup(pw.stop)
        cls.browser = getattr(pw, os.getenv('TEST_BROWSER', 'chromium')).launch()
        cls.addClassCleanup(cls.browser.close)

    def setUp(self):
        self.page = self.browser.new_page()
        self.addCleanup(self.page.close)
        requests = []
        self.page.context.on('request', lambda req: requests.append((req.url, req.method)))
        self.addCleanup(lambda: self.assertEqual([(u, m) for u, m in requests if m != 'GET' or
                        not (u.startswith(self.origin + '/') or u.startswith('blob:'))], []))
        self.page.goto(self.origin + '/blank.html')
        self.page.evaluate('''async () => {
          window.formats = await import('./Paint/formats.js');
          window.canvas = (w,h) => Object.assign(document.createElement('canvas'), {width:w,height:h});
          window.decode = async b => {
            const img = await formats.decodeImage(b), c = canvas(img.width,img.height), ctx = c.getContext('2d');
            ctx.drawImage(img,0,0); img.close?.();
            const pixel = x => [...ctx.getImageData(x,0,1,1).data];
            return [c.width,c.height,pixel(0),pixel(c.width-1)];
          };
          window.blobFrom64 = b64 => new Blob([Uint8Array.from(atob(b64), c => c.charCodeAt(0))]);
        }''')

    def test_independent_images(self):
        for name, data in FIXTURES.items():
            with self.subTest(name=name):
                result = self.page.evaluate('b64 => decode(blobFrom64(b64))', data)
                self.assertEqual(result, [5, 3, [238, 34, 51, 255], [238, 34, 51, 255]])

    def test_oriented_transparent_png(self):
        exif = bytes.fromhex('49492a0008000000010012010300010000000600000000000000')
        png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 2, 8, 6, 0, 0, 0)) +
               chunk(b'eXIf', exif) + chunk(b'IDAT', zlib.compress(bytes.fromhex('00ff0000ff0000000000'))) + chunk(b'IEND', b''))
        result = self.page.evaluate('b64 => decode(blobFrom64(b64))', base64.b64encode(png).decode())
        self.assertEqual(result, [2, 1, [0, 0, 0, 0], [255, 0, 0, 255]])

    def test_exports_match_signatures_dimensions_and_matte(self):
        for ext, magic, mime in [('png', '89504e47', 'image/png'), ('JPEG', 'ffd8ff', 'image/jpeg'),
                                 ('bmp', '424d', 'image/bmp'), ('.tiff', '49492a00', 'image/tiff'),
                                 ('webp', '52494646', 'image/webp'), ('ico', '00000100', 'image/x-icon')]:
            with self.subTest(ext=ext):
                kind, header, pixels = self.page.evaluate('''async ext => {
                  const c = canvas(512,128), ctx=c.getContext('2d');
                  ctx.fillStyle='#ff0000';ctx.fillRect(256,0,256,128);
                  const b=await formats.encodeImage(c,ext), bytes=new Uint8Array(await b.slice(0,12).arrayBuffer());
                  return [b.type,[...bytes].map(x=>x.toString(16).padStart(2,'0')).join(''),await decode(b)];
                }''', ext)
                self.assertEqual(kind, mime)
                self.assertTrue(header.startswith(magic), header)
                self.assertEqual(pixels[:2], [256, 64] if ext == 'ico' else [512, 128])
                matte = ext in ['JPEG', 'bmp']
                self.assertEqual(pixels[2], [255, 255, 255, 255] if matte else [0, 0, 0, 0])
                self.assertTrue(all(abs(a-b) <= 4 for a, b in zip(pixels[3], [255, 0, 0, 255])), pixels[3])

    def test_webp_fallback_never_relabels_png(self):
        self.assertEqual(self.page.evaluate('''async () => {
          const c=canvas(5,3); c.getContext('2d').fillRect(0,0,5,3);
          c.toBlob = f => HTMLCanvasElement.prototype.toBlob.call(c,f,'image/png');
          const out=await formats.encodeImage(c,'webp');
          const s=String.fromCharCode(...new Uint8Array(await out.slice(0,12).arrayBuffer()));
          return [s.slice(0,4),s.slice(8),await decode(out)];
        }'''), ['RIFF', 'WEBP', [5, 3, [0, 0, 0, 255], [0, 0, 0, 255]]])

    def test_invalid_bodies_and_size_limits(self):
        def png(w, h):
            return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
        # Valid dimension-bearing headers are sufficient to hit the size guard;
        # none of these files contain a decodable raster.
        bmp = bytearray(54); bmp[:2] = b'BM'; struct.pack_into('<Iii', bmp, 14, 40, 4097, 1)
        jpeg = bytes.fromhex('ffd8ffc0000b080001100101011100')
        tiff = bytearray(base64.b64decode(FIXTURES['tif']))
        first_ifd = struct.unpack_from('<I', tiff, 4)[0]; struct.pack_into('<H', tiff, first_ifd + 10, 4097)
        webp = b'RIFF'+struct.pack('<I', 22)+b'WEBPVP8X'+struct.pack('<I',10)+bytes.fromhex('00000000001000000000')
        ico = bytearray(base64.b64decode(FIXTURES['ico'])); ico[18:22] = b'\xff' * 4
        for data, oversized in [(b'<svg/>', False), (png(1, 1), False), (png(4097, 1), True),
                                (png(2049, 2048), True), (b'GIF89a'+struct.pack('<HH', 1, 5000)+bytes(4), True),
                                (bmp, True), (jpeg, True), (tiff, True), (webp, True), (ico, False)]:
            with self.subTest(prefix=data[:12]):
                msg = self.page.evaluate('''async b => {try {await formats.decodeImage(blobFrom64(b));return null;}
                                             catch(e){return e.message;}}''', base64.b64encode(data).decode())
                self.assertTrue(msg)
                if oversized:
                    self.assertIn('4096', msg)
        self.assertTrue(self.page.evaluate('''async () => {try {await formats.encodeImage(canvas(2,2),'gif');return false;}
                                                             catch(e){return !!e.message;}}'''))
