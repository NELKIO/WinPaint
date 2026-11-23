// The ribbon owns presentation only; document state and commands belong to the editor.
const tools = [
  ['pencil', 'Карандаш'], ['fill', 'Заливка цветом'], ['text', 'Текст'],
  ['eraser', 'Ластик'], ['picker', 'Выбор цвета'], ['magnifier', 'Масштаб'],
];
const shapes = [
  ['line', 'Линия'], ['curve', 'Кривая'], ['oval', 'Овал'], ['rect', 'Прямоугольник'],
  ['rrect', 'Скруглённый прямоугольник'], ['triangle', 'Треугольник'], ['rtriangle', 'Прямоугольный треугольник'],
  ['diamond', 'Ромб'], ['pentagon', 'Пятиугольник'], ['hexagon', 'Шестиугольник'],
  ['arrow_r', 'Стрелка вправо'], ['arrow_l', 'Стрелка влево'], ['arrow_u', 'Стрелка вверх'], ['arrow_d', 'Стрелка вниз'],
  ['star4', 'Четырёхконечная звезда'], ['star5', 'Пятиконечная звезда'], ['star6', 'Шестиконечная звезда'],
  ['callout_round', 'Закруглённая выноска'], ['callout_rect', 'Прямоугольная выноска'], ['callout_cloud', 'Овальная выноска'],
  ['heart', 'Сердце'], ['lightning', 'Молния'],
];
const brushes = [
  ['round', 'Кисть'], ['calligraphy1', 'Каллиграфическая кисть 1'], ['calligraphy2', 'Каллиграфическая кисть 2'],
  ['airbrush', 'Распылитель'], ['oil', 'Масляная кисть'], ['crayon', 'Восковой мелок'], ['marker', 'Маркер'], ['watercolor', 'Акварель'],
];
const palette = ['#000000','#7f7f7f','#880015','#ed1c24','#ff7f27','#fff200','#22b14c','#00a2e8','#3f48cc','#a349a4',
  '#ffffff','#c3c3c3','#b97a57','#ffaec9','#ffc90e','#efe4b0','#b5e61d','#99d9ea','#7092be','#c8bfe7'];
const widths = [[1,'1 пиксель'],[3,'3 пикселя'],[5,'5 пикселей'],[8,'8 пикселей'],[12,'12 пикселей']];
const prop = (key, options) => options.map(([value,label]) => ({key, value, label}));
const cmd = (command, label, shortcut, arg) => ({command, label, shortcut, arg});
const menus = {
  file: [cmd('new','Создать','Ctrl+N'),cmd('open','Открыть…','Ctrl+O'),cmd('save','Сохранить','Ctrl+S'),
    cmd('saveAs','Сохранить как…'),null,cmd('print','Печать…','Ctrl+P'),null,cmd('exit','Выход')],
  select: [...prop('tool',[['select','Прямоугольная область']]),cmd('selectAll','Выделить всё','Ctrl+A'),null,cmd('delete','Удалить','Del')],
  rotate: [cmd('rotate','Повернуть на 90° по часовой',null,90),cmd('rotate','Повернуть на 90° против часовой',null,-90),
    cmd('rotate','Повернуть на 180°',null,180),null,cmd('flip','Отразить по горизонтали',null,'h'),cmd('flip','Отразить по вертикали',null,'v')],
  brush: prop('brush',brushes), outline: prop('outline',[['none','Нет контура'],['solid','Сплошной цвет']]),
  fill: prop('fill',[['none','Нет заливки'],['solid','Сплошной цвет']]), width: prop('width',widths),
};
const $ = id => document.getElementById(id);
function iconButton(key, id, label) {
  const button = document.createElement('button');
  button.dataset[key] = id;
  button.setAttribute('aria-label', label);
  button.title = label;
  const img = document.createElement('img');
  img.src = new URL(`./icons/${id}.png`, import.meta.url).href;
  img.alt = '';
  button.append(img);
  return button;
}
function swatch(button, color, index) {
  button.dataset.color = color;
  button.style.setProperty('--swatch', color);
  const label = `${index === undefined ? 'Цвет' : `Пользовательский цвет ${index + 1}:`} ${color}`;
  button.setAttribute('aria-label', label);
  button.title = `${label} (левая кнопка — Цвет 1, правая — Цвет 2)`;
}
function showText(element, value) {
  if (element.textContent !== value) element.textContent = value;
}
export function initRibbon(app) {
  const ribbon = $('ribbon'), statusbar = $('statusbar'), canvas = $('canvas');
  $('tools').append(...tools.map(([id, label]) => iconButton('tool', id, label)));
  $('shapes').append(...shapes.map(([id, label]) => iconButton('shape', id, label)));
  const custom = [];
  for (const [index, color] of [...palette, ...Array(10).fill('#ffffff')].entries()) {
    const b = document.createElement('button'); b.className = 'swatch';
    const n = index - palette.length;
    swatch(b, color, n < 0 ? undefined : n);
    if (n >= 0) custom.push(b);
    $('palette').append(b);
  }
  for (const key of ['color1', 'color2']) {
    const input = $(key);
    input.addEventListener('input', () => app.set(key, input.value));
    input.addEventListener('change', () => {
      app.set(key, input.value);
      const n = Math.max(0, custom.findIndex(b => b.dataset.color === '#ffffff'));
      swatch(custom[n], input.value, n);
    });
  }
  $('palette').addEventListener('contextmenu', event => {
    const b = event.target.closest('[data-color]');
    if (b) { event.preventDefault(); app.set('color2', b.dataset.color); }
  });

  const popup = document.createElement('div');
  popup.className = 'ribbon-menu'; popup.id = 'ribbon-popup'; popup.hidden = true;
  popup.setAttribute('role', 'menu'); document.body.append(popup);
  let opener = null;
  for (const b of ribbon.querySelectorAll('[data-menu]')) {
    b.setAttribute('aria-haspopup', 'menu'); b.setAttribute('aria-expanded','false'); b.setAttribute('aria-controls',popup.id);
  }
  function closeMenu(restoreFocus = false) {
    if (!opener) return;
    opener.setAttribute('aria-expanded','false');
    if (restoreFocus) opener.focus({preventScroll:true});
    opener = null; popup.hidden = true;
  }
  function openMenu(button) {
    if (opener === button) { closeMenu(true); return; }
    closeMenu(); opener = button; button.setAttribute('aria-expanded','true');
    popup.replaceChildren(); popup.setAttribute('aria-label',button.getAttribute('aria-label') || button.textContent);
    for (const item of menus[button.dataset.menu]) {
      if (!item) { popup.append(document.createElement('hr')); continue; }
      const b = document.createElement('button'); b.tabIndex = -1;
      b.setAttribute('role', item.key ? 'menuitemradio' : 'menuitem');
      if (item.key) {
        b.dataset[item.key] = item.value;
        b.setAttribute('aria-checked', String(app.state[item.key] === item.value));
      } else { b.dataset.command = item.command; if (item.arg !== undefined) b.dataset.arg = item.arg; }
      if (item.key === 'width') {
        const line = document.createElement('span'); line.className = 'menu-sample'; line.style.height = `${item.value}px`; b.append(line);
      }
      b.append(document.createTextNode(item.label));
      if (item.shortcut) { const k = document.createElement('kbd'); k.textContent = item.shortcut; k.setAttribute('aria-hidden','true'); b.append(k); }
      b.onclick = () => { closeMenu(true); if (item.key) app.set(item.key, item.value); else app.run(item.command,item.arg); };
      popup.append(b);
    }
    popup.hidden = false;
    placeMenu();
    (popup.querySelector('[aria-checked="true"]') || popup.querySelector('button')).focus({preventScroll:true});
  }
  function placeMenu() {
    if (!opener) return;
    const rect = opener.getBoundingClientRect();
    if (rect.right <= 0 || rect.left >= innerWidth) { closeMenu(); return; }
    const above = rect.top - 4, below = innerHeight - rect.bottom - 4;
    const placeAbove = popup.scrollHeight > below && above > below;
    popup.style.maxHeight = `${Math.max(40,placeAbove ? above : below)}px`;
    popup.style.left = `${Math.max(4, Math.min(rect.left, innerWidth - popup.offsetWidth - 4))}px`;
    popup.style.top = `${placeAbove ? Math.max(4, rect.top - popup.offsetHeight) : rect.bottom}px`;
  }
  document.addEventListener('pointerdown', e => { if (opener && !opener.contains(e.target) && !popup.contains(e.target)) closeMenu(); });
  document.addEventListener('focusin', e => { if (opener && !opener.contains(e.target) && !popup.contains(e.target)) closeMenu(); });
  window.addEventListener('resize', () => closeMenu());
  ribbon.querySelector('.ribbon-scroll').addEventListener('scroll', placeMenu);
  popup.addEventListener('keydown', e => {
    if (e.key === 'Escape' || e.key === 'Tab') { closeMenu(true); if (e.key === 'Escape') {e.preventDefault(); e.stopPropagation();} return; }
    const buttons = [...popup.querySelectorAll('button')], i = buttons.indexOf(document.activeElement);
    const to = {ArrowDown: (i+1)%buttons.length, ArrowUp: (i+buttons.length-1)%buttons.length, Home:0, End:buttons.length-1}[e.key];
    if (to !== undefined) { e.preventDefault(); buttons[to].focus(); }
  });

  const tabs = [...ribbon.querySelectorAll('[role=tab]')];
  function switchTab(target) {
    closeMenu();
    for (const tab of tabs) {
      const current = target === tab;
      tab.setAttribute('aria-selected',String(current)); tab.tabIndex = current ? 0 : -1;
      $(tab.getAttribute('aria-controls')).hidden = !current;
    }
    ribbon.querySelector('.ribbon-scroll').scrollLeft = 0;
  }
  ribbon.addEventListener('keydown', e => {
    if (tabs.includes(e.target) && ['ArrowLeft','ArrowRight','Home','End'].includes(e.key)) {
      e.preventDefault(); const next = e.key === 'Home' ? tabs[0] : e.key === 'End' ? tabs[1] : tabs[1-tabs.indexOf(e.target)];
      switchTab(next); next.focus();
    } else if (e.target.dataset.menu && e.key === 'ArrowDown') { e.preventDefault(); openMenu(e.target); }
  });
  function handleButton(event) {
    const b = event.target.closest('button'); if (!b) return;
    const d = b.dataset;
    if (d.menu) openMenu(b);
    else if (tabs.includes(b)) switchTab(b);
    else if (d.command) app.run(d.command);
    else if (d.tool) app.set('tool', d.tool);
    else if (d.shape) app.set('shape', d.shape);
    else if (d.color) app.set('color1', d.color);
    else if (b.id === 'edit-colors') $('color1').click();
    else if (d.zoom) app.set('zoom', d.zoom === 'reset' ? 1 : Math.max(.1, Math.min(8, app.state.zoom * (d.zoom === 'in' ? 1.25 : .8))));
  }
  ribbon.addEventListener('click',handleButton); statusbar.addEventListener('click',handleButton);
  $('show-status').onchange = e => app.set('showStatus',e.target.checked);
  $('grid').onchange = e => {
    app.set('grid',e.target.checked);
    if (app.state.grid && app.state.zoom < 2) app.set('zoom',4);
  };
  const slider = $('zoom-slider');
  slider.oninput = () => app.set('zoom',.1 * Math.pow(80, Number(slider.value)/100));

  const toolButtons = [...ribbon.querySelectorAll('[data-tool], [data-menu="brush"]')];
  const shapeButtons = [...ribbon.querySelectorAll('[data-shape]')];
  const message = statusbar.querySelector('[role=status]');
  let lastTool, lastShape;
  function render() {
    const s = app.state;
    const title = `${s.dirty ? '*' : ''}${s.filename || 'Безымянный'} — Paint`;
    if (document.title !== title) document.title = title;
    showText($('caption'),title);
    if (s.tool !== lastTool || s.shape !== lastShape) {
      for (const b of toolButtons) b.setAttribute('aria-pressed', String(s.tool === (b.dataset.tool || 'brush')));
      for (const b of shapeButtons) b.setAttribute('aria-pressed', String(s.tool === 'shape' && s.shape === b.dataset.shape));
      lastTool = s.tool; lastShape = s.shape;
    }
    $('undo').disabled = !(s.canUndo || s.selectionPending); $('redo').disabled = !s.canRedo;
    for (const key of ['color1','color2']) if (s[key] && $(key).value !== s[key]) $(key).value = s[key];
    ribbon.style.setProperty('--pen-width', `${s.width}px`);
    $('grid').checked = Boolean(s.grid);
    const show = s.showStatus !== false; $('show-status').checked = show; statusbar.hidden = !show;
    const percent = `${Math.round(s.zoom*100)}%`;
    showText($('zoom-value'),percent); slider.value = Math.round(Math.log(s.zoom/.1)/Math.log(80)*100);
    slider.setAttribute('aria-valuetext',percent); slider.style.setProperty('--zoom-fill',`${slider.value}%`);
    showText($('dimensions'),`${canvas.width} × ${canvas.height} пикс`);
    showText($('coordinates'),s.x != null && s.y != null ? `${s.x}, ${s.y} пикс` : '');
    const sz = s.selectionSize;
    showText($('selection-size'), sz ? `${sz.width ?? sz.w ?? sz[0]} × ${sz.height ?? sz.h ?? sz[1]} пикс` : '');
    showText(message,s.status || '');
  }
  document.addEventListener('paint:update',render);
  render();
}
