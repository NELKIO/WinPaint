import {bitmap, checkSize, makeDocument, transform} from './document.js';
import {sizeDialog, saveDialog, discardDialog} from './dialogs.js';
// File codecs are needed only when the user opens or saves a picture.
const formats = () => import('./formats.js');
import {createDrawing} from './drawing.js';
import {createSelection} from './selection.js';
import {initRibbon} from './ribbon.js';

const $ = id => document.getElementById(id);
const canvas = $('canvas'), surface = $('surface'), workspace = $('workspace');
const css = document.createElement('link'); css.rel='stylesheet'; css.href=new URL('./document.css',import.meta.url); document.head.append(css);
const state = {tool:'pencil', brush:'round', shape:'line', width:3, color1:'#000000', color2:'#ffffff', outline:'solid', fill:'none', zoom:1, grid:false, showStatus:true, status:'', filename:'', dirty:false, x:null,y:null, selectionSize:null, canUndo:false, canRedo:false};
let busy=false, pointer=null, selection, drawing, active=null, drag=null, oldGeometry='';
const eraserTip=document.createElement('div'); eraserTip.className='eraser-tip'; eraserTip.hidden=true; surface.append(eraserTip);
const grid=document.createElement('div'); grid.className='pixel-grid'; surface.append(grid);
function update() {
  const {zoom,tool} = state, w=canvas.width*zoom, h=canvas.height*zoom;
  const geometry=`${w}/${h}/${zoom}`;
  if(oldGeometry!==geometry) {
    oldGeometry=geometry; canvas.style.width=surface.style.width=`${w}px`; canvas.style.height=surface.style.height=`${h}px`;
    selection?.refresh();
  }
  grid.hidden = !state.grid || zoom<2; grid.style.backgroundSize=`${zoom}px ${zoom}px`;
  canvas.style.imageRendering=zoom>1?'pixelated':'auto';
  canvas.style.cursor=tool==='text'?'text':tool==='magnifier'?'zoom-in':'crosshair';
  if(tool!=='eraser') eraserTip.hidden=true;
  document.dispatchEvent(new Event('paint:update'));
}
function message(text){ state.status=text; update(); }
const doc=makeDocument(canvas,state,update);
function finish() { active=null; pointer=null; drawing?.finish(); selection?.finish(); }
function cancel() { active=null; pointer=null; drawing?.cancel(); selection?.cancel(); }
function set(key,value) {
  if(key==='tool'||key==='brush'||key==='shape') {
    if(key!=='tool'||value!==state.tool) finish();
    if(key!=='tool') state.tool=key;
  }
  if(key==='zoom') { value=Math.min(8,Math.max(.1,Number(value))); if(!Number.isFinite(value)) return; }
  state[key]=value; update();
}
const app={...doc,state,set,run,update,message,canPaste:()=>!busy && !drag && pointer===null};
drawing=createDrawing(app); selection=createSelection(app); initRibbon(app);
doc.reset(bitmap(960,540,true));

function position(e) {
  const r=canvas.getBoundingClientRect();
  return {x:Math.floor((e.clientX-r.left)*canvas.width/r.width),y:Math.floor((e.clientY-r.top)*canvas.height/r.height)};
}
canvas.onpointerleave=()=>{eraserTip.hidden=true;};
canvas.oncontextmenu=e=>e.preventDefault();
canvas.tabIndex=-1;
canvas.onpointerdown=e=>{
  if(busy || pointer!==null || drag || ![0,2].includes(e.button)) return;
  e.preventDefault(); canvas.focus({preventScroll:true}); pointer=e.pointerId; canvas.setPointerCapture(pointer); state.status='';
  active=['select','text'].includes(state.tool)?selection:drawing;
  active.down(position(e),e); update();
};
canvas.onpointermove=e=>{
  if(pointer!==null && pointer!==e.pointerId) return;
  const p=position(e); state.x=p.x; state.y=p.y;
  if(active) active.move(p,e); else if(state.tool==='select') selection.move(p,e);
  if(state.tool==='eraser') {
    const side=Math.max(4,state.width*4)*state.zoom;
    Object.assign(eraserTip.style,{left:`${p.x*state.zoom}px`,top:`${p.y*state.zoom}px`,width:`${side}px`,height:`${side}px`});
    eraserTip.hidden=false;
  }
  // Pointer coordinates change frequently; don't rebuild the ribbon on each sample.
  $('coordinates').textContent=`${p.x}, ${p.y} пикс`;
};
canvas.onpointerup=e=>{if(pointer===e.pointerId){const target=active; active=null; pointer=null; target?.up(position(e),e); update();}};
canvas.onpointercancel=canvas.onlostpointercapture=e=>{if(pointer===e.pointerId) cancel();};
workspace.addEventListener('wheel',e=>{if(e.ctrlKey||e.metaKey){e.preventDefault(); set('zoom',state.zoom*(e.deltaY<0?1.25:.8));}},{passive:false});

for(const edge of ['e','s','se']) {
  const handle=document.createElement('span'); handle.id=`handle-${edge}`; handle.className='canvas-handle'; handle.title='Изменить размер холста'; surface.append(handle);
  handle.onpointerdown=e=>{
    if(e.button!==0||busy||pointer!==null||drag) return;
    e.preventDefault(); finish(); handle.setPointerCapture(e.pointerId);
    const box=document.createElement('div'); box.className='resize-outline'; surface.append(box);
    drag={id:e.pointerId,x:e.clientX,y:e.clientY,w:canvas.width,h:canvas.height,box};
  };
  function measure(e){return [Math.max(1,drag.w+(edge.includes('e')?Math.round((e.clientX-drag.x)/state.zoom):0)),Math.max(1,drag.h+(edge.includes('s')?Math.round((e.clientY-drag.y)/state.zoom):0))];}
  handle.onpointermove=e=>{if(drag?.id!==e.pointerId) return; const [w,h]=measure(e); drag.box.style.width=w*state.zoom+'px'; drag.box.style.height=h*state.zoom+'px'; state.selectionSize={width:w,height:h}; update();};
  handle.onpointerup=e=>{if(drag?.id!==e.pointerId) return; const [w,h]=measure(e); endDrag(); if(w!==canvas.width||h!==canvas.height){try {transform(doc,'resizeCanvas',w,h);}catch(err){message(err.message);}}};
  handle.onlostpointercapture=handle.onpointercancel=e=>{if(drag?.id===e.pointerId) endDrag();};
}
function endDrag(){drag?.box.remove();drag=null;state.selectionSize=null;update();}

function extension(name) {return name.split('.').pop().toLowerCase();}
async function save(as=false){
  let name=state.filename, ext=extension(name);
  if(as||!name||!['png','jpg','jpeg','bmp','webp','ico','tif','tiff'].includes(ext)){
    const result=await saveDialog(name); if(!result) return false;
    name=result.name; ext=result.extension;
  }
  const {encodeImage}=await formats();
  const blob=await encodeImage(canvas,ext), url=URL.createObjectURL(blob), link=document.createElement('a');
  link.href=url; link.download=name; document.body.append(link); link.click(); link.remove(); setTimeout(()=>URL.revokeObjectURL(url),60000);
  state.filename=name; doc.markSaved(); message(`Сохранён: ${name}`); return true;
}
async function canReplace(){
  if(!state.dirty) return true;
  const choice=await discardDialog(state.filename);
  return choice==='discard'||(choice==='save' && await save());
}
const fileInput=$('file'); fileInput.accept='.png,.jpeg,.jpg,.webp,.bmp,.gif,.tif,.tiff,.ico';
async function load(file){
  if(!file||busy||drag) return;
  busy=true;let image;
  try {
    const {decodeImage}=await formats(); image=await decodeImage(file); checkSize(image.width,image.height);
    finish(); if(!await canReplace()) return;
    state.filename=file.name; state.zoom=1; doc.reset(image); message(`Открыт: ${file.name}`);
  }catch(err){message(`Не удалось открыть ${file.name}: ${err.message}`);}
  finally{image?.close?.();busy=false;}
}
fileInput.onchange=()=>{const f=fileInput.files[0]; fileInput.value=''; void load(f);};
workspace.ondragover=e=>{if(e.dataTransfer.types.includes('Files')) e.preventDefault();};
workspace.ondrop=e=>{e.preventDefault();void load(e.dataTransfer.files[0]);};
async function run(command,arg) {
  if(busy||drag) return;
  if(command==='open'){fileInput.click(); return;}
  busy=true;
  try {
    if(['copy','cut','paste','delete','selectAll','crop'].includes(command)) {drawing.finish(); await selection.run(command,arg); return;}
    if(command==='undo' && doc.pending()){cancel(); doc.abort(); return;}
    finish();
    switch(command){
      case 'new': if(await canReplace()){state.filename='';state.zoom=1;doc.reset(bitmap(960,540,true)); message('');} break;
      case 'exit': if(await canReplace()){state.filename='';state.zoom=1;doc.reset(bitmap(960,540,true)); message('Документ закрыт');} break;
      case 'save': case 'saveAs': await save(command==='saveAs'); break;
      case 'print': window.print(); break;
      case 'undo': doc.undo(); break;
      case 'redo': doc.redo(); break;
      case 'rotate': case 'flip': transform(doc,command,arg); break;
      case 'resize': {const size=await sizeDialog(canvas.width,canvas.height); if(size) transform(doc,'resizeImage',...size); break;}
      case 'fullscreen': if(document.fullscreenElement) await document.exitFullscreen(); else if(document.documentElement.requestFullscreen) await document.documentElement.requestFullscreen(); else message('Полноэкранный режим недоступен в этом браузере'); break;
    }
  }catch(err){message(err.message);}finally{busy=false;update();}
}
document.addEventListener('keydown',e=>{
  if(e.defaultPrevented || document.querySelector('dialog[open]') || e.target.closest('input:not([type=range]),textarea,select,[contenteditable=true]')) return;
  const ctrl=e.ctrlKey||e.metaKey;
  const mapped={KeyN:'new',KeyO:'open',KeyS:e.shiftKey?'saveAs':'save',KeyP:'print',KeyZ:e.shiftKey?'redo':'undo',KeyY:'redo',KeyX:'cut',KeyC:'copy',KeyA:'selectAll'};
  const cmd=ctrl?mapped[e.code]:e.key==='Delete'?'delete':null;
  if(cmd){e.preventDefault();void run(cmd);}
  else if(e.key==='Escape'){if(!busy){if(drag) endDrag();cancel();update();}}
  else if(ctrl && ['+','=','-'].includes(e.key)){e.preventDefault();set('zoom',state.zoom*(e.key==='-'?.8:1.25));}
});
window.addEventListener('beforeunload',e=>{if(state.dirty||doc.pending()||state.selectionPending||document.querySelector('[contenteditable=true]')?.textContent){e.preventDefault();e.returnValue='';}});
