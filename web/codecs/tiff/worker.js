// tiff.js 1.0.0 (npm), LibTIFF/zlib; see LICENSE. Each job has its own fixed heap.
importScripts('./tiff.min.js');
self.onmessage = ({data: {buffer, width, height}}) => {
  let failed = false;
  try {
    Tiff.initialize({TOTAL_MEMORY: 128 * 1024 * 1024, printErr: line => {
      // LibTIFF can return partial pixels after a failed strip. Don't accept them.
      if (!/warning/i.test(line)) failed = true;
    }});
    const tiff = new Tiff({buffer});
    if (width !== tiff.width() || height !== tiff.height()) throw Error();
    const rgba = tiff.readRGBAImage();
    tiff.close();
    if (failed) throw Error();
    // TIFFReadRGBAImage returns associated alpha; ImageData expects straight alpha.
    const bytes = new Uint8ClampedArray(rgba);
    for (let i = 0; i < bytes.length; i += 4) {
      const a = bytes[i + 3];
      if (a > 0 && a < 255) for (let c = 0; c < 3; c++) bytes[i+c] *= 255 / a;
    }
    self.postMessage(rgba, [rgba]);
  } catch { self.postMessage(null); }
};
