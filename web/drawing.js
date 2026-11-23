// Image-space drawing tools. The host owns pointer capture, view scale and history.
const BRUSHES = {
  round: [2, 'round', 255], calligraphy1: [2.2, 'butt', 255], calligraphy2: [2.2, 'square', 255],
  oil: [3, 'round', 160], crayon: [2.4, 'round', 110], marker: [2.6, 'square', 120],
  watercolor: [3, 'round', 70]
};
const same = (a, b) => a.x === b.x && a.y === b.y;
const pixelPoint = p => ({x: Math.floor(p.x), y: Math.floor(p.y)});

function constrained(a, b, angle, shift) {
  if (!shift) return b;
  const dx = b.x-a.x, dy = b.y-a.y;
  if (angle) {
    const step = Math.PI/4, direction = Math.round(Math.atan2(dy,dx)/step)*step;
    const distance = Math.hypot(dx,dy);
    return {x:a.x+Math.round(distance*Math.cos(direction)), y:a.y+Math.round(distance*Math.sin(direction))};
  }
  const side = Math.max(Math.abs(dx), Math.abs(dy));
  return {x:a.x+(dx<0 ? -side : side), y:a.y+(dy<0 ? -side : side)};
}

function polygon(points) {
  const p = new Path2D();
  p.moveTo(...points[0]);
  for (const point of points.slice(1)) p.lineTo(...point);
  p.closePath();
  return p;
}

function shapePaths(shape, a, b, end) {
  const path = new Path2D();
  if (shape === 'line' || shape === 'curve') {
    path.moveTo(a.x, a.y);
    if (end) path.quadraticCurveTo(b.x,b.y,end.x,end.y);
    else path.lineTo(b.x,b.y);
    return [path];
  }
  // Desktop QRect includes both dragged pixels, regardless of drag direction.
  const x = Math.min(a.x,b.x), y = Math.min(a.y,b.y);
  const w = Math.abs(a.x-b.x)+1, h = Math.abs(a.y-b.y)+1, size = Math.min(w,h);
  const cx = x+w/2, cy = y+h/2;
  const point = (u,v) => [x+w*u, y+h*v];
  const poly = (...pairs) => polygon(pairs.map(([u,v]) => point(u,v)));
  switch (shape) {
    case 'oval': path.ellipse(cx,cy,w/2,h/2,0,0,Math.PI*2); break;
    case 'rect': path.rect(x,y,w,h); break;
    case 'rrect': path.roundRect(x,y,w,h,size*.2); break;
    case 'triangle': return [poly([.5,0],[1,1],[0,1])];
    case 'rtriangle': return [poly([0,0],[0,1],[1,1])];
    case 'diamond': return [poly([.5,0],[1,.5],[.5,1],[0,.5])];
    case 'pentagon': case 'hexagon': case 'star4': case 'star5': case 'star6': {
      const star = shape.startsWith('star');
      const count = star ? Number(shape.slice(-1))*2 : shape === 'pentagon' ? 5 : 6;
      const rotation = shape === 'hexagon' ? 0 : -Math.PI/2;
      const points = Array.from({length:count}, (_,i) => {
        const r = star && i%2 ? (count === 8 ? .38 : .42) : 1;
        const t = rotation+i*2*Math.PI/count;
        return [Math.floor((a.x+b.x)/2)+r*w/2*Math.cos(t), Math.floor((a.y+b.y)/2)+r*h/2*Math.sin(t)];
      });
      return [polygon(points)];
    }
    case 'arrow_r': case 'arrow_l': case 'arrow_u': case 'arrow_d': {
      // Construct one arrow in length/cross-axis coordinates, then orient it.
      const horizontal = shape === 'arrow_r' || shape === 'arrow_l';
      const len = horizontal ? w : h, half = (horizontal ? h : w)/2;
      const head = len-size*.5, t = size*.22;
      return [polygon([[0,-t],[head,-t],[head,-half],[len,0],[head,half],[head,t],[0,t]].map(([u,v]) => {
        if (horizontal) return [x+(shape === 'arrow_r' ? u : len-u), cy+v];
        return [cx+v, y+(shape === 'arrow_d' ? u : len-u)];
      }))];
    }
    case 'heart':
      path.moveTo(...point(.5,1));
      path.bezierCurveTo(...point(-.1,.45), ...point(.2,0), ...point(.5,.3));
      path.bezierCurveTo(...point(.8,0), ...point(1.1,.45), ...point(.5,1));
      break;
    case 'lightning': return [poly([.55,0],[.2,.5],[.45,.5],[.3,1],[.8,.4],[.5,.4])];
    case 'callout_round': case 'callout_rect': case 'callout_cloud': {
      const bubble = h*.75;
      if (shape === 'callout_cloud') path.ellipse(cx,y+bubble/2,w/2,bubble/2,0,0,2*Math.PI);
      else if (shape === 'callout_round') path.roundRect(x,y,w,bubble,size*.15);
      else path.rect(x,y,w,bubble);
      return [path, polygon([[x+w*.2,y+bubble-1],point(.15,1),[x+w*.38,y+bubble-1]])];
    }
    default: throw Error(`Unknown shape: ${shape}`);
  }
  return [path];
}

// Canvas strokes are always antialiased. Rasterize into a two-color coverage
// mask and threshold it for the desktop's crisp pencil/shape pixels. Only
// the affected rectangle is read or replaced; the saved patch erases previews.
function crispRenderer(canvas, ctx) {
  const mask = document.createElement('canvas');
  const m = mask.getContext('2d', {willReadFrequently:true});
  return function render(points, width, stroke, fill, paths) {
    if (stroke == null && fill == null) return null;
    const pad = Math.ceil(width/2)+3;
    const xs = points.map(p => p.x), ys = points.map(p => p.y);
    const x = Math.max(0,Math.min(...xs)-pad), y = Math.max(0,Math.min(...ys)-pad);
    const w = Math.min(canvas.width,Math.max(...xs)+pad+1)-x;
    const h = Math.min(canvas.height,Math.max(...ys)+pad+1)-y;
    if (w <= 0 || h <= 0) return null;
    if (mask.width !== w) mask.width = w;
    if (mask.height !== h) mask.height = h;
    m.resetTransform(); m.clearRect(0,0,w,h);
    const align = width%2 ? .5 : 0;
    m.translate(align-x,align-y);
    m.fillStyle='white'; m.strokeStyle='black';
    m.lineWidth=width; m.lineJoin='round'; m.lineCap='round';
    for (const path of paths) {
      if (fill != null) m.fill(path);
      if (stroke != null) m.stroke(path);
    }
    const before = ctx.getImageData(x,y,w,h), image = m.getImageData(0,0,w,h);
    const old = new Uint32Array(before.data.buffer), out = new Uint32Array(image.data.buffer);
    for (let i=0;i<out.length;i++) {
      out[i] = image.data[i*4+3] < 128 ? old[i] : image.data[i*4] < 128 ? stroke : fill;
    }
    ctx.putImageData(image,x,y);
    return {before,x,y};
  };
}

function softStroke(ctx, g, a, b) {
  ctx.save();
  const erase = g.tool === 'eraser', dot = same(a,b);
  ctx.fillStyle = ctx.strokeStyle = erase ? g.color2 : g.ink;
  if (!erase && g.brush === 'airbrush') {
    const radius = Math.max(2,g.width), length = Math.hypot(b.x-a.x,b.y-a.y);
    const steps = Math.max(1, Math.ceil(length/Math.max(1,radius/2)));
    for (let i=1;i<=steps;i++) {
      const x = a.x+(b.x-a.x)*i/steps, y = a.y+(b.y-a.y)*i/steps;
      for (let j=0;j<Math.max(3,radius*2);j++) {
        const r = Math.sqrt(Math.random())*radius, t = Math.random()*Math.PI*2;
        ctx.fillRect(Math.round(x+r*Math.cos(t)), Math.round(y+r*Math.sin(t)),1,1);
      }
    }
  } else {
    const [scale,cap,alpha] = erase ? [4,'square',255] : BRUSHES[g.brush];
    const w = erase ? Math.max(4,g.width*scale) : g.width*scale;
    ctx.lineWidth=w; ctx.lineCap=cap; ctx.globalAlpha=alpha/255;
    ctx.beginPath();
    if (!dot) { ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y); ctx.stroke(); }
    else if (cap === 'round') { ctx.arc(a.x,a.y,w/2,0,Math.PI*2); ctx.fill(); }
    else ctx.fillRect(a.x-w/2,a.y-w/2,w,w);
  }
  ctx.restore();
}

// Exact RGBA, four-connected scanline fill. Queue runs rather than every
// neighboring pixel; painting a run also marks it visited.
function flood(ctx, canvas, p, replacement) {
  const {width:w,height:h} = canvas;
  const image = ctx.getImageData(0,0,w,h), pixels = new Uint32Array(image.data.buffer);
  const start = p.y*w+p.x, target = pixels[start];
  if (target === replacement) return;
  const stack = [start];
  while (stack.length) {
    const seed = stack.pop();
    if (pixels[seed] !== target) continue;
    const row = seed-seed%w;
    let l=seed, r=seed+1;
    while (l>row && pixels[l-1]===target) l--;
    while (r<row+w && pixels[r]===target) r++;
    pixels.fill(replacement,l,r);
    for (const offset of [-w,w]) {
      if (row+offset < 0 || row+offset >= w*h) continue;
      let run = false;
      for (let i=l+offset;i<r+offset;i++) {
        const hit = pixels[i] === target;
        if (hit && !run) stack.push(i);
        run = hit;
      }
    }
  }
  ctx.putImageData(image,0,0);
}

export function createDrawing(app) {
  const {canvas,ctx,state} = app;
  const crisp = crispRenderer(canvas,ctx);
  const swatch = document.createElement('canvas'); swatch.width=swatch.height=1;
  const chip = swatch.getContext('2d',{willReadFrequently:true});
  function colorWord(color) {
    chip.fillStyle=color; chip.fillRect(0,0,1,1);
    return new Uint32Array(chip.getImageData(0,0,1,1).data.buffer)[0];
  }
  let g = null;
  function colors(right) {
    g.ink = right ? state.color2 : state.color1;
    const ink = colorWord(g.ink), paper = colorWord(right ? state.color1 : state.color2);
    g.fill = state.fill === 'solid' ? paper : null;
    g.stroke = state.outline === 'none' ? g.fill : ink;
    g.pencil = ink;
  }
  function stroke(a,b) {
    if (g.tool !== 'pencil') { softStroke(ctx,g,a,b); return; }
    if (same(a,b)) {
      // A zero-length canvas subpath has no stroke, so stamp the round nib.
      const nib = new Path2D(); nib.arc(a.x,a.y,g.width/2,0,Math.PI*2);
      if (g.width === 1) { ctx.save(); ctx.fillStyle=g.ink; ctx.fillRect(a.x,a.y,1,1); ctx.restore(); }
      else crisp([a],g.width,null,g.pencil,[nib]);
    } else crisp([a,b],g.width,g.pencil,null,shapePaths('line',a,b));
  }
  function preview(b) {
    if (g.patch) ctx.putImageData(g.patch.before,g.patch.x,g.patch.y);
    const {shape,start,end,width} = g, open = shape === 'curve' || shape === 'line';
    const points = end ? [start,b,end] : [start,b];
    g.patch = crisp(points,width,g.stroke,open ? null : g.fill,shapePaths(shape,start,b,end));
  }
  function down(pos,e) {
    if (e.button !== 0 && e.button !== 2) return;
    const p = pixelPoint(pos), right = e.button === 2;
    if (g) {
      if (g.phase === 'waiting') { g.phase='bend'; colors(right); preview(p); }
      return;
    }
    const {tool,brush,shape,color2} = state, ink = right ? color2 : state.color1;
    if (tool === 'magnifier') { app.set('zoom',Math.min(8,Math.max(.1,state.zoom*(right ? .8 : 1.25)))); return; }
    if (p.x<0 || p.x>=canvas.width || p.y<0 || p.y>=canvas.height) return;
    if (tool === 'picker' || tool === 'fill') {
      const rgba = ctx.getImageData(p.x,p.y,1,1).data;
      if (tool === 'picker') {
        app.set(right ? 'color2' : 'color1','#'+Array.from(rgba.slice(0,3),v=>v.toString(16).padStart(2,'0')).join(''));
      } else {
        const replacement = colorWord(ink);
        if (new Uint32Array(rgba.buffer)[0] !== replacement) app.change(() => flood(ctx,canvas,p,replacement));
      }
      return;
    }
    if (!['brush','pencil','eraser','shape'].includes(tool)) return;
    g = {tool,brush,shape,color2,width:Number(state.width),start:p,last:p,phase:'drag'};
    colors(right);
    if (tool === 'shape' && g.stroke == null && g.fill == null) { g=null; return; }
    app.begin();
    if (tool !== 'shape') stroke(p,p);
  }
  function move(pos,e) {
    if (!g || g.phase === 'waiting') return;
    const p = pixelPoint(pos);
    if (g.tool === 'shape') {
      const angle = g.shape === 'line' || g.shape === 'curve';
      g.last = g.phase === 'bend' ? p : constrained(g.start,p,angle,e.shiftKey);
      preview(g.last);
    } else if (!same(g.last,p)) { stroke(g.last,p); g.last=p; }
  }
  function up(pos,e) {
    if (!g || g.phase === 'waiting') return;
    move(pos,e);
    if (g.tool === 'shape' && g.shape === 'curve' && g.phase === 'drag') {
      g.end=g.last; g.phase='waiting';
    } else { g=null; app.commit(); }
  }
  function cancel() { if (g) { g=null; app.abort(); } }
  function finish() {
    if (!g) return;
    if (g.tool === 'shape' && (!g.patch || g.shape === 'curve')) cancel();
    else { g=null; app.commit(); }
  }
  return {down,move,up,cancel,finish};
}
