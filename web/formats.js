// File bytes, not the extension or a caller-supplied MIME type, select the decoder.
import {bitmap, checkSize} from './document.js';

const mime = {png:'image/png', jpeg:'image/jpeg', bmp:'image/bmp', gif:'image/gif',
  tiff:'image/tiff', webp:'image/webp', ico:'image/x-icon'};
const invalid = () => Error('Повреждённое или неподдерживаемое изображение.');
function requireValid(ok) { if (!ok) throw invalid(); }
const text = (b, i, n) => String.fromCharCode(...b.subarray(i,i+n));
const view = b => new DataView(b.buffer, b.byteOffset, b.byteLength);
const u24 = (b,i) => b[i] + b[i+1]*256 + b[i+2]*65536;

function identify(b) {
  if (text(b,0,8) === '\x89PNG\r\n\x1a\n') return 'png';
  if (text(b,0,3) === '\xff\xd8\xff') return 'jpeg';
  if (text(b,0,2) === 'BM') return 'bmp';
  if (['GIF89a','GIF87a'].includes(text(b,0,6))) return 'gif';
  if (['II*\0','MM\0*'].includes(text(b,0,4))) return 'tiff';
  if (text(b,0,4) === 'RIFF' && text(b,8,4) === 'WEBP') return 'webp';
  if (text(b,0,4) === '\0\0\x01\0') return 'ico';
  throw invalid();
}

// Read only the first classic TIFF directory. Do not follow EXIF/thumbnail/page links.
function directory(b) {
  requireValid(identify(b) === 'tiff');
  const d = view(b), le = b[0] === 73, offset = d.getUint32(4, le), n = d.getUint16(offset, le);
  requireValid(offset >= 8 && offset + 2 + 12*n + 4 <= b.length);
  const tags = new Map();
  for (let j = 0; j < n; j++) {
    const i = offset+2+12*j, tag = d.getUint16(i,le), type = d.getUint16(i+2,le);
    if (![256,257,259,274].includes(tag)) continue;
    requireValid(!tags.has(tag) && (type === 3 || type === 4) && d.getUint32(i+4,le) === 1);
    tags.set(tag, type === 3 ? d.getUint16(i+8,le) : d.getUint32(i+8,le));
    // The caller applies orientation exactly once after decoding, including axes 5–8.
    if (tag === 274) {
      if (type === 3) d.setUint16(i+8,1,le); else d.setUint32(i+8,1,le);
    }
  }
  return tags;
}

function orient(src, value) {
  const w=src.width, h=src.height;
  const matrices = {2:[-1,0,0,1,w,0], 3:[-1,0,0,-1,w,h], 4:[1,0,0,-1,0,h],
    5:[0,1,1,0,0,0], 6:[0,1,-1,0,h,0], 7:[0,-1,-1,0,h,w], 8:[0,-1,1,0,0,w]};
  if (!matrices[value]) return src;
  const c = value >= 5 ? bitmap(h,w) : bitmap(w,h), ctx = c.getContext('2d');
  ctx.setTransform(...matrices[value]); ctx.drawImage(src,0,0);
  return c;
}

async function nativeDecode(blob,w,h,allowSwap=false) {
  checkSize(w,h);
  const img = new Image(), url = URL.createObjectURL(blob);
  try {
    img.src = url; await img.decode();
    const dw = img.naturalWidth, dh = img.naturalHeight;
    requireValid((dw === w && dh === h) || (allowSwap && dw === h && dh === w));
    // A canvas is a static first-frame snapshot, even when the input is animated.
    const c = bitmap(dw,dh); c.getContext('2d').drawImage(img,0,0); return c;
  } finally { URL.revokeObjectURL(url); }
}

async function png(b) {
  const d = view(b);
  requireValid(d.getUint32(8) === 13 && text(b,12,4) === 'IHDR');
  const w = d.getUint32(16), h = d.getUint32(20); checkSize(w,h);
  // Some engines auto-rotate PNG, others ignore eXIf. Strip the metadata before
  // native decode, then apply its orientation in one predictable coordinate system.
  let start=0, orientation=1;
  const parts=[];
  for (let i=8; i+12<=b.length;) {
    const len=d.getUint32(i), type=text(b,i+4,4), end=i+12+len;
    requireValid(end<=b.length);
    if (type==='eXIf') {
      requireValid(!parts.length);
      parts.push(b.subarray(start,i)); start=end;
      try { orientation=directory(b.subarray(i+8,end-4)).get(274) || 1; } catch { /* optional metadata */ }
    }
    if (type==='IEND') {
      requireValid(len===0); parts.push(b.subarray(start,end));
      return orient(await nativeDecode(new Blob(parts,{type:mime.png}),w,h),orientation);
    }
    i=end;
  }
  throw invalid();
}

function jpegSize(b) {
  const d=view(b);
  for (let i=2; i<b.length;) {
    requireValid(b[i++]===0xff); while (b[i]===0xff) i++;
    const marker=b[i++]; requireValid(marker!==0xda && marker!==0xd9);
    const len=d.getUint16(i); requireValid(len>=2 && i+len<=b.length);
    if (marker>=0xc0 && marker<=0xcf && ![0xc4,0xc8,0xcc].includes(marker)) {
      requireValid(len>=8); return [d.getUint16(i+5),d.getUint16(i+3)];
    }
    i+=len;
  }
  throw invalid();
}

function dibSize(b) {
  const d=view(b), len=d.getUint32(0,true);
  if (len===12) return [d.getUint16(4,true),d.getUint16(6,true)];
  requireValid(len>=40 && len<=b.length);
  return [d.getInt32(4,true),Math.abs(d.getInt32(8,true))];
}

function gifFirst(b) {
  const d=view(b), w=d.getUint16(6,true), h=d.getUint16(8,true); checkSize(w,h);
  const table=flags => flags&128 ? 3*(2<<(flags&7)) : 0;
  let i=13+table(b[10]);
  function subBlocks() {
    while (i<b.length) { const n=b[i++]; if (!n) return; i+=n; }
    throw invalid();
  }
  while (i<b.length) {
    const type=b[i++];
    if (type===0x21) { i++; subBlocks(); continue; }
    requireValid(type===0x2c);
    const fw=d.getUint16(i+4,true), fh=d.getUint16(i+6,true); checkSize(fw,fh);
    requireValid(d.getUint16(i,true)+fw<=w && d.getUint16(i+2,true)+fh<=h);
    i+=9+table(b[i+8])+1; subBlocks();
    return nativeDecode(new Blob([b.subarray(0,i),Uint8Array.of(0x3b)],{type:mime.gif}),w,h);
  }
  throw invalid();
}

function webpSize(b) {
  const d=view(b), end=d.getUint32(4,true)+8; requireValid(end<=b.length);
  let size;
  for (let i=12;i+8<=end;) {
    const type=text(b,i,4), n=d.getUint32(i+4,true), p=i+8;
    requireValid(p+n<=end);
    let w,h;
    if (type==='VP8X' || type==='ANMF') {
      requireValid(n >= (type==='VP8X'?10:16));
      const s=p+(type==='VP8X'?4:6); w=1+u24(b,s); h=1+u24(b,s+3);
    } else if (type==='VP8L') {
      requireValid(n>=5 && b[p]===0x2f);
      const bits=d.getUint32(p+1,true); w=1+(bits&0x3fff); h=1+((bits>>>14)&0x3fff);
    } else if (type==='VP8 ') {
      requireValid(n>=10 && text(b,p+3,3)==='\x9d\x01\x2a');
      w=d.getUint16(p+6,true)&0x3fff; h=d.getUint16(p+8,true)&0x3fff;
    }
    if (w!==undefined) { checkSize(w,h); size ??= [w,h]; requireValid(w<=size[0] && h<=size[1]); }
    i=p+n+(n%2);
  }
  requireValid(size); return size;
}

// Icon DIBs stack a color bitmap over a 1-bit transparency mask. Decode the
// color plane as BMP because native ICO readers disagree on non-square icons.
async function iconDib(data,w,h) {
  const d=view(data), header=d.getUint32(0,true), core=header===12;
  const bpp=d.getUint16(core?10:14,true), compression=core?0:d.getUint32(16,true);
  requireValid([1,4,8,16,24,32].includes(bpp) && [0,3].includes(compression));
  const colors=(!core && d.getUint32(32,true)) || (bpp<=8 ? 2**bpp : 0);
  const offset=header+colors*(core?3:4)+(header===40 && compression===3 ? 12 : 0);
  const stride=4*Math.ceil(w*bpp/32), maskStride=4*Math.ceil(w/32), mask=offset+stride*h;
  requireValid(mask<=data.length && (bpp===32 || mask+maskStride*h<=data.length));
  const bmp=new Uint8Array(14+mask); bmp.set([66,77]); bmp.set(data.subarray(0,mask),14);
  const bd=view(bmp); bd.setUint32(2,bmp.length,true); bd.setUint32(10,14+offset,true);
  const topDown=!core && d.getInt32(8,true)<0;
  if (core) bd.setUint16(20,h,true); else bd.setInt32(22,topDown?-h:h,true);
  const c=await nativeDecode(new Blob([bmp],{type:mime.bmp}),w,h);
  const ctx=c.getContext('2d'), img=ctx.getImageData(0,0,w,h);
  let hasAlpha=false;
  if (bpp===32 && compression===0) {
    for (let i=offset+3;i<mask;i+=4) if (data[i]) { hasAlpha=true; break; }
  }
  for (let y=0;y<h;y++) for (let x=0;x<w;x++) {
    const row=topDown?y:h-y-1, p=(y*w+x)*4+3;
    if (hasAlpha) img.data[p]=data[offset+row*stride+x*4+3];
    else if (data[mask+row*maskStride+(x>>3)] & (128>>(x%8))) img.data[p]=0;
  }
  ctx.putImageData(img,0,0); return c;
}

async function ico(b) {
  const d=view(b), n=d.getUint16(4,true); requireValid(n && 6+n*16<=b.length);
  let best;
  for (let i=6; i<6+n*16;i+=16) {
    const w=b[i]||256, h=b[i+1]||256, len=d.getUint32(i+8,true), off=d.getUint32(i+12,true);
    requireValid(off>=6+n*16 && len && off+len<=b.length);
    if (!best || w*h>best.w*best.h) best={w,h,len,off};
  }
  const {w,h,len,off}=best, data=b.subarray(off,off+len);
  if (text(data,0,8)==='\x89PNG\r\n\x1a\n') {
    const p=view(data); requireValid(p.getUint32(16)===w && p.getUint32(20)===h); return png(data);
  }
  const [dw,dh]=dibSize(data); requireValid(dw===w && dh===2*h);
  return iconDib(data,w,h);
}

async function tiff(b) {
  const tags=directory(b), w=tags.get(256), h=tags.get(257); checkSize(w,h);
  // Each decode has a bounded lifetime and heap, regardless of strip compression.
  const worker=new Worker(new URL('./codecs/tiff/worker.js',import.meta.url));
  let timer;
  try {
    const rgba=await new Promise((resolve,reject) => {
      timer=setTimeout(()=>reject(invalid()),15000);
      worker.onerror=()=>reject(invalid()); worker.onmessage=e=>e.data ? resolve(e.data) : reject(invalid());
      worker.postMessage({buffer:b.buffer,width:w,height:h},[b.buffer]);
    });
    requireValid(rgba.byteLength===w*h*4);
    const c=bitmap(w,h); c.getContext('2d').putImageData(new ImageData(new Uint8ClampedArray(rgba),w,h),0,0);
    return orient(c,tags.get(274));
  } finally { clearTimeout(timer); worker.terminate(); }
}

export async function decodeImage(file) {
  if (file.size>64*1024*1024) throw Error('Допустимый размер файла — до 64 МБ.');
  try {
    const b=new Uint8Array(await file.arrayBuffer()), kind=identify(b);
    if (kind==='png') return await png(b);
    if (kind==='gif') return await gifFirst(b);
    if (kind==='ico') return await ico(b);
    if (kind==='tiff') return await tiff(b);
    const size=kind==='jpeg' ? jpegSize(b) : kind==='bmp' ? dibSize(b.subarray(14)) : webpSize(b);
    return await nativeDecode(new Blob([b],{type:mime[kind]}),...size,kind!=='bmp');
  } catch (e) {
    if (e instanceof RangeError || e instanceof TypeError || e instanceof DOMException) throw invalid();
    throw e;
  }
}

function encodeBmp(c) {
  const {width:w,height:h}=c, stride=Math.ceil(w*3/4)*4, b=new Uint8Array(54+stride*h), d=view(b);
  b.set([66,77]); d.setUint32(2,b.length,true); d.setUint32(10,54,true); d.setUint32(14,40,true);
  d.setUint32(18,w,true); d.setUint32(22,h,true); d.setUint16(26,1,true); d.setUint16(28,24,true);
  d.setUint32(34,stride*h,true);
  const data=c.getContext('2d').getImageData(0,0,w,h).data;
  for (let y=0;y<h;y++) for (let x=0, p=4*y*w, out=54+(h-1-y)*stride; x<w; x++,p+=4,out+=3) {
    b[out]=data[p+2]; b[out+1]=data[p+1]; b[out+2]=data[p];
  }
  return new Blob([b],{type:mime.bmp});
}

function encodeTiff(c) {
  // Baseline, little-endian, one uncompressed strip, RGBA with unassociated alpha.
  const {width:w,height:h}=c, fields=11, bits=8+2+12*fields+4, strip=bits+8;
  const header=new Uint8Array(strip), d=view(header); header.set([73,73,42,0,8,0,0,0]);
  d.setUint16(8,fields,true);
  const entries=[[256,4,1,w],[257,4,1,h],[258,3,4,bits],[259,3,1,1],[262,3,1,2],
    [273,4,1,strip],[277,3,1,4],[278,4,1,h],[279,4,1,w*h*4],[284,3,1,1],[338,3,1,2]];
  entries.forEach(([tag,type,count,value],j)=>{
    const i=10+j*12; d.setUint16(i,tag,true); d.setUint16(i+2,type,true); d.setUint32(i+4,count,true);
    if (type===3 && count===1) d.setUint16(i+8,value,true); else d.setUint32(i+8,value,true);
  });
  for (let i=bits;i<strip;i+=2) d.setUint16(i,8,true);
  return new Blob([header,c.getContext('2d').getImageData(0,0,w,h).data],{type:mime.tiff});
}

async function canvasBlob(c,kind) {
  const blob=await new Promise(resolve=>c.toBlob(resolve,mime[kind],0.95));
  if (blob && blob.type===mime[kind]) {
    const b=new Uint8Array(await blob.slice(0,16).arrayBuffer());
    try { if (identify(b)===kind) return blob; } catch { /* try fallback */ }
  }
  return null;
}

let webpModule;
async function encodeWebP(c) {
  // @jsquash/webp 1.5.0, non-SIMD encoder only. All runtime assets are same-origin.
  const [{default:load},{defaultOptions}] = await Promise.all([
    import('./codecs/webp/webp_enc.js'), import('./codecs/webp/meta.js')]);
  const mod=await (webpModule ??= load());
  const {width:w,height:h}=c, data=c.getContext('2d').getImageData(0,0,w,h);
  const out=mod.encode(data.data,w,h,{...defaultOptions,lossless:1,method:2});
  requireValid(out && identify(out)==='webp');
  const [dw,dh]=webpSize(out); requireValid(dw===w && dh===h);
  return new Blob([out],{type:mime.webp});
}

export async function encodeImage(canvas,extension) {
  const ext=String(extension).toLowerCase().replace(/^\./,''), kind=ext==='jpg'?'jpeg':ext==='tif'?'tiff':ext;
  if (!['png','jpeg','bmp','tiff','webp','ico'].includes(kind)) throw Error('Неподдерживаемый формат сохранения.');
  const {width:w,height:h}=canvas; checkSize(w,h);
  try {
    let c=canvas;
    if (kind==='bmp' || kind==='jpeg') {
      c=bitmap(w,h,true); c.getContext('2d').drawImage(canvas,0,0);
    }
    if (kind==='bmp') return encodeBmp(c);
    if (kind==='tiff') return encodeTiff(c);
    if (kind==='ico') {
      const scale=Math.min(1,256/Math.max(w,h));
      if (scale<1) { c=bitmap(Math.max(1,Math.round(w*scale)),Math.max(1,Math.round(h*scale)));
        c.getContext('2d').drawImage(canvas,0,0,c.width,c.height); }
      const data=await canvasBlob(c,'png'); requireValid(data);
      const header=new Uint8Array(22), d=view(header); header.set([0,0,1,0,1,0,c.width&255,c.height&255,0,0,1,0,32,0]);
      d.setUint32(14,data.size,true); d.setUint32(18,22,true);
      return new Blob([header,data],{type:mime.ico});
    }
    const blob=await canvasBlob(c,kind);
    if (blob) return blob;
    if (kind==='webp') return await encodeWebP(c);
    throw invalid();
  } catch { throw Error(`Не удалось сохранить изображение в формате ${kind.toUpperCase()}.`); }
}
