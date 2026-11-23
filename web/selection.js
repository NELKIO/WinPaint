import {bitmap} from './document.js';

const $ = id => document.getElementById(id);
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
function extract(source, x = 0, y = 0, w = source.width, h = source.height) {
  const result = bitmap(w, h);
  result.getContext('2d').drawImage(source, x, y, w, h, 0, 0, w, h);
  return result;
}
function textNodes(element) {
  const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT), nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  return nodes;
}

// The browser handles shaping, selection, IME, and line layout. Read the visual
// bounds of each styled run before removing the editor; rasterize in image pixels.
function paintText(editor, ctx, origin, scale) {
  const base = editor.getBoundingClientRect(), range = document.createRange();
  ctx.save();
  ctx.textBaseline = 'alphabetic';
  for (const node of textNodes(editor)) {
    const style = getComputedStyle(node.parentElement), size = parseFloat(style.fontSize);
    ctx.font = `${style.fontStyle} ${style.fontWeight} ${size}px ${style.fontFamily}`;
    ctx.fillStyle = style.color;
    ctx.direction = style.direction;
    ctx.textAlign = 'left';
    const metrics = ctx.measureText('Mg');
    const ascent = metrics.fontBoundingBoxAscent ?? size * .8;
    const descent = metrics.fontBoundingBoxDescent ?? size * .2;
    let underlined = false;
    for (let el = node.parentElement; el; el = el.parentElement) {
      underlined ||= getComputedStyle(el).textDecorationLine.includes('underline');
      if (el === editor) break;
    }
    for (const match of node.data.matchAll(/[^\n\t]+/g)) {
      range.setStart(node, match.index); range.setEnd(node, match.index + match[0].length);
      const bounds = range.getBoundingClientRect();
      const x = origin.x + (bounds.left - base.left) / scale.x;
      const y = origin.y + (bounds.top - base.top + bounds.height/2) / scale.y + (ascent-descent)/2;
      ctx.fillText(match[0], x, y);
      if (underlined) ctx.fillRect(x, y + Math.max(1,size/16), bounds.width / scale.x, Math.max(1,size/14));
    }
  }
  ctx.restore();
}

function makeTextEditor(app, layer, scale) {
  const bar = $('textbar');
  const defaults = {fontFamily:'sans-serif', fontSize:'14px', fontWeight:'normal', fontStyle:'normal', textDecorationLine:'none'};
  let editor = null, origin, savedRange;
  function element(tag, attrs, parent) {
    const el = document.createElement(tag);
    for (const [name, value] of Object.entries(attrs)) el.setAttribute(name, value);
    parent.append(el);
    return el;
  }
  function label(name) { const lbl = element('label', {}, bar); lbl.append(`${name}: `); return lbl; }
  const fonts = element('select', {'aria-label':'Шрифт'}, label('Шрифт'));
  // FontFaceSet.check() also succeeds for missing local fonts. A real face
  // produces the same metrics with either fallback; a missing one does not.
  const measure = document.createElement('canvas').getContext('2d');
  const metrics = (name, fallback) => { measure.font = `32px "${name}", ${fallback}`; return measure.measureText('Широкий Wimi.').width; };
  const candidates = ['Arial','Times New Roman','Courier New','Georgia','Verdana','Tahoma','Trebuchet MS','Comic Sans MS','Impact',
    'DejaVu Sans','DejaVu Serif','DejaVu Sans Mono','Liberation Serif','Liberation Sans','Liberation Mono','Ubuntu','Noto Sans',
    'Helvetica Neue','Helvetica','Menlo','Avenir','Optima'];
  for (const [value, name] of [['sans-serif','Без засечек'], ['serif','С засечками'], ['monospace','Моноширинный'],
    ...candidates.filter(f => metrics(f,'serif') === metrics(f,'monospace')).map(f => [f,f])]) {
    element('option', {value}, fonts).textContent = name;
  }
  const sizeInput = element('input', {type:'number', min:4, max:400, step:1,list:'text-sizes','aria-label':'Размер шрифта'}, label('Размер'));
  const sizes = element('datalist', {id:'text-sizes'}, bar);
  for (const value of [8,9,10,11,12,14,16,18,20,24,28,32,36,48,72]) element('option', {value}, sizes);
  sizeInput.style.width = '5em';
  const toggles = [
    ['fontWeight','bold','Полужирный','Ж'], ['fontStyle','italic','Курсив','К'], ['textDecorationLine','underline','Подчёркнутый','Ч']
  ].map(([key, value, name, letter]) => {
    const button = element('button', {type:'button', title:name,'aria-label':name}, bar);
    button.textContent = letter; button.style[key] = value;
    button.addEventListener('mousedown', e => e.preventDefault());
    button.onclick = () => format(key, button.getAttribute('aria-pressed') === 'true' ? (key === 'textDecorationLine' ? 'none' : 'normal') : value);
    return {key,value,button};
  });
  const hint = element('span', {}, bar); hint.textContent = 'Выберите текст для форматирования';
  bar.hidden = true;

  function currentRange() {
    const sel = window.getSelection();
    if (!editor || !sel.rangeCount) return null;
    const r = sel.getRangeAt(0);
    return editor.contains(r.commonAncestorContainer) ? r : null;
  }
  function controls() {
    if (!editor) return;
    let el = savedRange?.startContainer || editor;
    if (el.nodeType === Node.TEXT_NODE) el = el.parentElement;
    const style = getComputedStyle(el);
    fonts.value = style.fontFamily.replace(/^['"]|['"]$/g,'');
    if (document.activeElement !== sizeInput) sizeInput.value = parseFloat(style.fontSize);
    for (const {key,value,button} of toggles) {
      const on = key === 'fontWeight' ? (style[key] === 'bold' || Number(style[key]) >= 600) : style[key] === value;
      button.setAttribute('aria-pressed', String(on));
    }
  }
  function rememberRange() {
    if (document.activeElement !== editor) return;
    const r = currentRange();
    if (r) { savedRange = r.cloneRange(); controls(); }
  }
  document.addEventListener('selectionchange', rememberRange);
  bar.addEventListener('pointerdown', rememberRange);

  function format(key, value) {
    if (!editor) return;
    defaults[key] = value;
    const range = savedRange?.cloneRange() || document.createRange();
    const all = !savedRange || range.collapsed;
    if (all) range.selectNodeContents(editor);
    // Split only the two boundary text nodes and style the resulting spans.
    // Flatten each formatted run's style so partial un-underlining also works
    // (CSS text-decoration on an ancestor cannot be cancelled on a descendant).
    const parts = textNodes(editor).filter(n => range.intersectsNode(n)).map(n => [n,
      n === range.startContainer ? range.startOffset : 0, n === range.endContainer ? range.endOffset : n.length]);
    let first, last;
    for (let [n, start, end] of parts) {
      if (end <= start) continue;
      const style = getComputedStyle(n.parentElement), span = document.createElement('span');
      for (const k of Object.keys(defaults)) span.style[k] = style[k];
      span.style[key] = value;
      if (end < n.length) n.splitText(end);
      if (start) n = n.splitText(start);
      // Our spans contain just one text run. Split any previous formatted
      // wrapper rather than nesting (especially important for underlining).
      const old = n.parentElement;
      if (old.matches('[data-text-run]')) {
        const after = old.cloneNode(false);
        while (n.nextSibling) after.append(n.nextSibling);
        old.after(span, after); span.append(n);
        if (!old.hasChildNodes()) old.remove();
        if (!after.hasChildNodes()) after.remove();
      } else { n.before(span); span.append(n); }
      span.dataset.textRun = '';
      first ||= n; last = n;
    }
    // Put whole-field defaults on unformatted caret input, but keep underline
    // on individual runs to allow removing it on part of a selection later.
    if (all && (!first || key !== 'textDecorationLine')) editor.style[key] = value;
    if (key === 'textDecorationLine' && editor.style.textDecorationLine === 'underline' && first) {
      // Transfer the default underline to unaffected text before clearing it.
      for (const n of textNodes(editor)) if (!n.parentElement.closest('[data-text-run]')) {
        const span = document.createElement('span'); span.dataset.textRun = ''; span.style.textDecorationLine = 'underline'; n.before(span); span.append(n);
      }
      editor.style.textDecorationLine = 'none';
    }
    editor.focus({preventScroll:true});
    if (first) { range.setStart(first,0); range.setEnd(last,last.length); }
    else range.selectNodeContents(editor);
    if (all) range.collapse(false);
    const sel = getSelection(); sel.removeAllRanges(); sel.addRange(range); rememberRange();
  }
  fonts.onchange = () => format('fontFamily', fonts.value);
  function applySize() {
    const value = sizeInput.valueAsNumber;
    if (!Number.isFinite(value)) { sizeInput.value = parseFloat(defaults.fontSize); return; }
    format('fontSize', `${clamp(Math.round(value),4,400)}px`);
  }
  sizeInput.onchange = applySize;
  // Blur fires change exactly once; do not re-enter format() while it is
  // replacing a selected span and restoring the browser's Range.
  sizeInput.onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); sizeInput.blur(); } };

  function refresh() {
    if (!editor) return;
    const z = scale();
    Object.assign(editor.style, {left:`${origin.x*z.x}px`, top:`${origin.y*z.y}px`, transform:`scale(${z.x},${z.y})`});
  }
  function start(p) {
    editor = element('div', {contenteditable:'true', role:'textbox', 'aria-multiline':'true', 'aria-label':'Текст', spellcheck:'false'}, layer);
    Object.assign(editor.style, defaults, {position:'absolute', pointerEvents:'auto', userSelect:'text', touchAction:'auto', cursor:'text',
      transformOrigin:'top left', minWidth:'120px', width:'max-content', whiteSpace:'pre', lineHeight:'normal',
      padding:'0', margin:'0', border:'0', outline:'1px dashed #2977bf', color:app.state.color1});
    origin = p; savedRange = null; bar.hidden = false; refresh(); editor.focus({preventScroll:true}); controls();
    editor.addEventListener('keydown', e => { if (e.key === 'Escape' && !e.isComposing) { e.preventDefault(); e.stopPropagation(); close(false); } });
    // Paste text, not external HTML, links, images or arbitrary embedded styles.
    editor.addEventListener('paste', e => { e.preventDefault(); e.stopPropagation();
      const text = e.clipboardData?.getData('text/plain'); if (text) document.execCommand('insertText', false, text); });
    editor.addEventListener('drop', e => e.preventDefault());
  }
  function close(commit) {
    if (!editor) return;
    if (commit && editor.textContent.trim()) app.change(() => paintText(editor, app.ctx, origin, scale()));
    editor.remove(); editor = savedRange = null; bar.hidden = true;
  }
  return {start, close, refresh};
}

export function createSelection(app) {
  const {canvas, ctx, state} = app, surface = $('surface');
  const style = document.createElement('style');
  style.textContent = `
    #textbar:not([hidden]) {display:flex; flex-wrap:wrap; align-items:center; gap:6px; padding:3px 8px;
      background:#eef3fb; border-bottom:1px solid #cdd8ea; font-size:12px}
    #textbar button {min-width:28px; min-height:26px; border:1px solid #c0ccdf; border-radius:3px; background:white}
    #textbar button[aria-pressed=true] {background:#cfe3fb; border-color:#7fb0ec}
    .selection-frame {position:absolute; inset:0; width:100%; height:100%; pointer-events:none}
    .selection-frame rect {x:.5px; y:.5px; width:calc(100% - 1px); height:calc(100% - 1px); fill:none; stroke:white}
    .selection-frame rect:last-child {stroke:#151515; stroke-dasharray:4 4}
    @media(prefers-reduced-motion:no-preference) {.selection-frame rect:last-child {animation:selection-march .8s linear infinite}}
    @keyframes selection-march {to {stroke-dashoffset:-8}}
  `;
  document.head.append(style);
  const layer = document.createElement('div');
  Object.assign(layer.style, {position:'absolute', inset:'0', overflow:'hidden', pointerEvents:'none'});
  surface.append(layer);
  const box = document.createElement('div'); box.hidden = true;
  Object.assign(box.style, {position:'absolute', pointerEvents:'none', boxSizing:'border-box'});
  const svg = name => document.createElementNS('http://www.w3.org/2000/svg',name);
  const frame = svg('svg'); frame.setAttribute('aria-hidden','true'); frame.setAttribute('class','selection-frame');
  frame.append(svg('rect'),svg('rect')); box.append(frame); layer.append(box);
  const scale = () => { const r = canvas.getBoundingClientRect(); return {x:r.width/canvas.width, y:r.height/canvas.height}; };
  const text = makeTextEditor(app, layer, scale);
  let rect = null, picture = null, lifted = false, floating = false, gesture = null, clipboard = null, internalOnly = false, generation = 0;
  const contains = (r,p) => r && p.x >= r.x && p.y >= r.y && p.x < r.x+r.w && p.y < r.y+r.h;
  function clipped(r) {
    const x = Math.max(0,r.x), y = Math.max(0,r.y);
    return {x,y,w:Math.max(0, Math.min(canvas.width,r.x+r.w)-x),h:Math.max(0, Math.min(canvas.height,r.y+r.h)-y)};
  }
  const integer = p => ({x:Math.floor(p.x), y:Math.floor(p.y)});
  function refresh() {
    text.refresh(); box.hidden = !rect;
    if (!rect) return;
    const z = scale(); Object.assign(box.style, {left:`${rect.x*z.x}px`,top:`${rect.y*z.y}px`,width:`${rect.w*z.x}px`,height:`${rect.h*z.y}px`});
  }
  function show() {
    state.selectionSize = rect ? {width:rect.w,height:rect.h} : null;
    state.selectionPending = floating;
    refresh(); app.update();
  }
  function clear() {
    picture?.remove(); rect = picture = gesture = null; lifted = floating = false;
    if (canvas.style.cursor === 'move') canvas.style.removeProperty('cursor');
    show();
  }
  function preview() {
    Object.assign(picture.style,{display:'block',width:'100%',height:'100%',margin:'0',border:'0',pointerEvents:'none', imageRendering:'pixelated'});
    box.prepend(picture); floating = true;
  }
  function erase(r) { ctx.save(); ctx.fillStyle = state.color2; ctx.fillRect(r.x,r.y,r.w,r.h); ctx.restore(); }
  function cancel() { generation++; text.close(false); if (lifted) app.abort(); clear(); }
  function finish() {
    generation++; text.close(true);
    if (floating) {
      const draw = () => ctx.drawImage(picture,rect.x,rect.y);
      if (lifted && lifted.x === rect.x && lifted.y === rect.y) app.abort();
      else if (lifted) { draw(); app.commit(); }
      else if (clipped(rect).w && clipped(rect).h) app.change(draw);
    }
    clear();
  }
  function down(point, e) {
    if (e && e.button !== 0) return;
    const p = integer(point);
    if (state.tool === 'text') { finish(); text.start(p); return; }
    if (state.tool !== 'select') return;
    generation++;
    if (contains(rect,p)) gesture = {move:true, dx:p.x-rect.x, dy:p.y-rect.y};
    else { finish(); gesture = {start:p}; rect = {...p,w:1,h:1}; show(); }
  }
  function move(point) {
    const p = integer(point);
    if (!gesture) {
      if (state.tool === 'select') { if (contains(rect,p)) canvas.style.cursor='move'; else if (canvas.style.cursor==='move') canvas.style.removeProperty('cursor'); }
      return;
    }
    if (gesture.move) {
      const x = p.x-gesture.dx, y = p.y-gesture.dy;
      if (rect.x === x && rect.y === y) return;
      if (!floating) { picture = extract(canvas,rect.x,rect.y,rect.w,rect.h); app.begin(); lifted = {...rect}; erase(rect); preview(); }
      Object.assign(rect,{x,y});
    } else {
      const start = gesture.start; rect = clipped({x:Math.min(start.x,p.x), y:Math.min(start.y,p.y), w:Math.abs(p.x-start.x)+1, h:Math.abs(p.y-start.y)+1});
    }
    show();
  }
  function up(p) { if (gesture) { move(p); if (!gesture.move && (rect.w < 2 || rect.h < 2)) clear(); gesture = null; } }
  function remove() {
    if (!rect) return;
    if (!floating) app.change(() => erase(rect));
    else if (lifted) app.commit(); // The original area was erased when lifted.
    clear();
  }
  async function copy() {
    clipboard = picture || (rect ? extract(canvas,rect.x,rect.y,rect.w,rect.h) : extract(canvas));
    internalOnly = true;
    if (!navigator.clipboard?.write || !window.ClipboardItem) { app.message('Скопировано в буфер редактора'); return; }
    try {
      // Start write during the user gesture (WebKit requires this for permission).
      const png = new Promise((resolve,reject) => clipboard.toBlob(b => b ? resolve(b) : reject(Error()),'image/png'));
      await navigator.clipboard.write([new ClipboardItem({'image/png':png})]);
      internalOnly = false; app.message('Изображение скопировано');
    } catch { app.message('Скопировано в буфер редактора. Системный буфер недоступен.'); }
  }
  function float(image) {
    finish(); app.set('tool','select'); picture = image;
    rect = {x:0,y:0,w:image.width,h:image.height}; preview(); show();
  }
  const nativePasteAllowed = () => !document.querySelector('dialog[open]') && (!app.canPaste || app.canPaste());
  async function fromBlob(blob, token, native = false) {
    if (!blob || blob.size > 32*1024*1024) throw Error('слишком большой файл');
    const image = await createImageBitmap(blob);
    try {
      if (token === generation && (!native || nativePasteAllowed())) {
        const pixels = extract(image); clipboard = pixels; internalOnly = false; float(pixels);
      }
    } finally { image.close(); }
  }
  async function paste() {
    const token = ++generation;
    if (!internalOnly && navigator.clipboard?.read) {
      let items = [];
      try { items = await navigator.clipboard.read(); }
      catch { /* Permission can be denied even on HTTPS; keep internal paste usable. */ }
      for (const item of items) {
        const type = item.types.find(t => t === 'image/png') || item.types.find(t => t.startsWith('image/'));
        if (type) {
          try { await fromBlob(await item.getType(type),token); }
          catch (err) { app.message(`Не удалось вставить: ${err.message}`); }
          return;
        }
      }
    }
    if (token !== generation) return;
    if (clipboard) float(clipboard); else app.message('Изображение недоступно. Скопируйте его и нажмите Ctrl+V.');
  }
  document.addEventListener('paste', e => {
    if (e.defaultPrevented || !nativePasteAllowed() || e.target.closest?.('input,textarea,select,[contenteditable]')) return;
    const file = Array.from(e.clipboardData?.files || []).find(f => f.type.startsWith('image/')) ||
      Array.from(e.clipboardData?.items || []).find(i => i.kind === 'file' && i.type.startsWith('image/'))?.getAsFile();
    if (file) { e.preventDefault(); fromBlob(file,++generation,true).catch(err => app.message(`Не удалось вставить: ${err.message}`)); }
    else if (clipboard) { e.preventDefault(); float(clipboard); }
  });
  function run(cmd) {
    switch (cmd) {
      case 'copy': return copy();
      case 'cut': if (rect) { const write = copy(); remove(); return write; } break;
      case 'paste': return paste();
      case 'delete': remove(); break;
      case 'selectAll': finish(); app.set('tool','select'); rect = {x:0,y:0,w:canvas.width,h:canvas.height}; show(); break;
      case 'crop': if (rect) {
        const r = clipped(rect);
        if (!r.w || !r.h) { app.message('Выделение вне холста'); break; }
        finish(); app.change(() => app.replaceBitmap(extract(canvas,r.x,r.y,r.w,r.h)));
      } break;
    }
  }
  return {down,move,up,cancel,finish,run,refresh};
}
