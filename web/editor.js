'use strict';
const $ = id => document.getElementById(id);
const canvas = document.querySelector('canvas');
const ctx = canvas.getContext('2d', {willReadFrequently: true});
const statusLine = document.querySelector('[role=status]');
const undo = [], redo = [];
const historyBudget = 64 * 1024 * 1024;
let tool = 'brush', stroke = null, busy = false;
ctx.fillStyle = '#fff';
ctx.fillRect(0, 0, canvas.width, canvas.height);

function controls() {
  $('undo').disabled = busy || !!stroke || !undo.length;
  $('redo').disabled = busy || !!stroke || !redo.length;
  $('open').disabled = $('save').disabled = busy || !!stroke;
}
function snapshot() { return ctx.getImageData(0, 0, canvas.width, canvas.height); }
function restore(from, to) {
  if (busy || stroke || !from.length) return;
  to.push(snapshot());
  ctx.putImageData(from.pop(), 0, 0);
  controls();
}
$('undo').onclick = () => restore(undo, redo);
$('redo').onclick = () => restore(redo, undo);
for (const name of ['brush', 'eraser']) {
  $(name).onclick = () => {
    tool = name;
    for (const id of ['brush', 'eraser']) $(id).setAttribute('aria-pressed', String(id === tool));
  };
}
$('size').oninput = () => { $('size-value').value = `${$('size').value} px`; };
function point(e) {
  const r = canvas.getBoundingClientRect();
  return [(e.clientX - r.left) * canvas.width / r.width, (e.clientY - r.top) * canvas.height / r.height];
}
canvas.onpointerdown = e => {
  if (busy || stroke || e.button !== 0) return;
  e.preventDefault();
  canvas.setPointerCapture(e.pointerId);
  redo.length = 0;
  const limit = Math.floor(historyBudget / (canvas.width * canvas.height * 4));
  while (undo.length >= limit) undo.shift();
  undo.push(snapshot());
  stroke = {id: e.pointerId, at: point(e)};
  ctx.lineWidth = Number($('size').value);
  ctx.fillStyle = ctx.strokeStyle = tool === 'brush' ? $('color').value : '#ffffff';
  ctx.lineCap = 'round';
  ctx.beginPath(); ctx.arc(...stroke.at, ctx.lineWidth / 2, 0, 2 * Math.PI); ctx.fill();
  controls();
};
function extend(e) {
  if (stroke?.id !== e.pointerId) return;
  const next = point(e);
  ctx.beginPath(); ctx.moveTo(...stroke.at); ctx.lineTo(...next); ctx.stroke();
  stroke.at = next;
}
canvas.onpointermove = extend;
function finish(e) {
  if (stroke?.id !== e.pointerId) return;
  if (e.type === 'pointerup') extend(e);
  stroke = null;
  controls();
}
canvas.onpointerup = canvas.onpointercancel = canvas.onlostpointercapture = finish;

$('open').onclick = () => $('file').click();
$('file').onchange = async () => {
  const file = $('file').files[0];
  $('file').value = '';
  if (!file || busy || stroke) return;
  busy = true; controls();
  let bitmap;
  try {
    if (file.size > 32 * 1024 * 1024) throw Error('файл больше 32 МиБ');
    const bytes = new Uint8Array(await file.slice(0, 24).arrayBuffer());
    const header = new DataView(bytes.buffer);
    if (bytes.length !== 24 || header.getUint32(0) !== 0x89504e47 || header.getUint32(4) !== 0x0d0a1a0a || header.getUint32(8) !== 13 || header.getUint32(12) !== 0x49484452) throw Error('это не PNG');
    const w = header.getUint32(16), h = header.getUint32(20);
    if (!w || !h || w > 4096 || h > 4096 || w*h > 4194304) throw Error('размер превышает лимит холста (4096 по стороне, 4 Мп)');
    bitmap = await createImageBitmap(file);
    if (bitmap.width !== w || bitmap.height !== h) throw Error('неверные размеры PNG');
    canvas.width = w; canvas.height = h;
    ctx.drawImage(bitmap, 0, 0);
    undo.length = redo.length = 0;
    $('dimensions').textContent = `${w} × ${h} px`;
    statusLine.textContent = `Открыт: ${file.name}`;
  } catch (error) { statusLine.textContent = `Не удалось открыть ${file.name}: ${error.message}`; }
  finally { bitmap?.close(); busy = false; controls(); }
};
$('save').onclick = () => {
  busy = true; controls();
  canvas.toBlob(blob => {
    busy = false; controls();
    if (!blob) { statusLine.textContent = 'Не удалось сохранить PNG'; return; }
    const url = URL.createObjectURL(blob), link = document.createElement('a');
    link.href = url; link.download = 'WinPaint.png'; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    statusLine.textContent = 'PNG передан для скачивания';
  }, 'image/png');
};
