// A history entry stores a document revision, including its dimensions.
export function checkSize(w, h) {
  if (![w, h].every(n => Number.isInteger(n) && n >= 1 && n <= 4096) || w*h > 4194304)
    throw Error('Допустимо до 4096 пикселей по стороне и до 4 Мп на рисунок.');
}
export function bitmap(w, h, white = false) {
  checkSize(w, h);
  const image = document.createElement('canvas'); image.width = w; image.height = h;
  if (white) { const p = image.getContext('2d'); p.fillStyle = '#fff'; p.fillRect(0, 0, w, h); }
  return image;
}
export function makeDocument(canvas, state, notify) {
  const ctx = canvas.getContext('2d', {willReadFrequently:true});
  let serial = 0, current = 0, saved = 0, before = null;
  const past = [], future = [];
  function snapshot() { return {id:current, image:ctx.getImageData(0, 0, canvas.width, canvas.height)}; }
  function sync() { state.dirty = current !== saved; state.canUndo = !!before || !!past.length; state.canRedo = !!future.length; notify(); }
  function replaceBitmap(image) {
    checkSize(image.width, image.height);
    canvas.width = image.width; canvas.height = image.height;
    ctx.drawImage(image, 0, 0);
  }
  function restore(entry) {
    canvas.width = entry.image.width; canvas.height = entry.image.height;
    ctx.putImageData(entry.image, 0, 0); current = entry.id;
  }
  function trim(stack) {
    let total = past.concat(future).reduce((v,e) => v + e.image.data.byteLength, 0);
    while ((total > 64 * 1024 * 1024 || past.length + future.length > 40) && stack.length > 1)
      total -= stack.shift().image.data.byteLength;
  }
  function begin() { if (!before) { before = snapshot(); sync(); } }
  function commit() {
    if (!before) return;
    past.push(before); before = null; future.length = 0; current = ++serial; trim(past); sync();
  }
  function abort() { if (before) { restore(before); before = null; sync(); } }
  function change(fn) { begin(); try { fn(); commit(); } catch (error) { abort(); throw error; } }
  function travel(from,to) {
    if (!from.length) return;
    to.push(snapshot()); restore(from.pop()); trim(to); sync();
  }
  return {canvas,ctx,replaceBitmap,begin,commit,abort,change,pending:()=>!!before,
    undo:() => travel(past,future), redo:() => travel(future,past),
    markSaved() { saved = current; sync(); },
    reset(image) { replaceBitmap(image); past.length = future.length = 0; before = null; current = saved = ++serial; sync(); }
  };
}
export function transform(doc, kind, a, b) {
  const src = doc.canvas;
  const quarter = kind === 'rotate' && Math.abs(a) === 90;
  const w = kind.startsWith('resize') ? a : quarter ? src.height : src.width;
  const h = kind.startsWith('resize') ? b : quarter ? src.width : src.height;
  const out = bitmap(w,h, kind === 'resizeCanvas'), p = out.getContext('2d');
  if (kind === 'rotate') { p.translate(w/2,h/2); p.rotate(a*Math.PI/180); p.translate(-src.width/2,-src.height/2); }
  if (kind === 'flip') { p.translate(a==='h'?w:0,a==='v'?h:0); p.scale(a==='h'?-1:1,a==='v'?-1:1); }
  p.drawImage(src, 0, 0, kind==='resizeImage'?w:src.width, kind==='resizeImage'?h:src.height);
  doc.change(() => doc.replaceBitmap(out));
}
