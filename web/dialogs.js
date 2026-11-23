import {checkSize} from './document.js';

function dialog(title, body, buttons, setup = () => {}) {
  const el = document.createElement('dialog'); el.className = 'paint-dialog';
  el.setAttribute('aria-label',title);
  const form = document.createElement('form'); form.method = 'dialog';
  // Only static templates are used here. User-supplied names are assigned as text/value.
  form.innerHTML = `<h2></h2><section>${body}</section><p class="dialog-error" role="alert"></p><footer></footer>`;
  form.querySelector('h2').textContent = title;
  for (const [value, caption] of buttons) {
    const button = document.createElement('button'); button.value = value; button.textContent = caption;
    if (value === 'cancel') button.formNoValidate = true;
    form.querySelector('footer').append(button);
  }
  el.append(form); document.body.append(el);
  const values = setup(form) || (()=>null);
  return new Promise(resolve => {
    function complete(result) { el.close(); el.remove(); resolve(result); }
    form.addEventListener('submit', e => {
      e.preventDefault();
      const button = e.submitter?.value || buttons[0][0];
      try { complete(button === 'cancel' ? null : {button, data:values()}); }
      catch (err) { form.querySelector('.dialog-error').textContent = err.message; }
    });
    el.addEventListener('cancel', e => { e.preventDefault(); complete(null); });
    el.showModal();
  });
}
export async function discardDialog(filename) {
  const res = await dialog('Paint', '<p></p>', [['save','Сохранить'],['discard','Не сохранять'],['cancel','Отмена']], f=>{
    f.querySelector('section p').textContent = `Сохранить изменения в «${filename || 'Безымянный'}»?`;
  });
  return res?.button;
}
export async function saveDialog(filename) {
  const result = await dialog('Сохранить как', `<label>Имя файла: <input name="filename" required></label>
    <label>Тип файла: <select name="format"></select></label>`, [['save','Сохранить'],['cancel','Отмена']], f=>{
    const name=f.elements.filename, format=f.elements.format;
    const types={png:'PNG',jpg:'JPEG',bmp:'Точечный рисунок',tiff:'TIFF',webp:'WebP',ico:'Значок'};
    for (const [id,label] of Object.entries(types)) format.add(new Option(`${label} (*.${id})`,id));
    const ext=s=>s.split('.').pop().toLowerCase().replace(/^jpeg$/,'jpg').replace(/^tif$/,'tiff');
    name.value=filename || 'Безымянный.png'; const suffix=ext(name.value);
    format.value=Object.hasOwn(types,suffix)?suffix:'png';
    format.onchange=()=>{name.value=(name.value.replace(/\.[^.]*$/,'') || 'Безымянный')+'.'+format.value;};
    name.oninput=()=>{const e=ext(name.value); if(Object.hasOwn(types,e)) format.value=e;};
    return ()=>{
      let value=name.value.trim(); if(!value || /[\\/]/.test(value)) throw Error('Введите имя файла без пути.');
      if(!value.includes('.') || ext(value)!==format.value) value=value.replace(/\.[^.]+$/,'')+'.'+format.value;
      return {name:value,extension:format.value};
    };
  });
  return result?.data;
}
export async function sizeDialog(w,h) {
  const result=await dialog('Изменение размеров и наклона', `<fieldset><legend>Изменить размер</legend>
    <div><label><input type="radio" name="mode" value="percent" checked>Проценты</label> <label><input type="radio" name="mode" value="pixels">Пиксели</label></div>
    <label>По горизонтали: <input name="w" type="number" min="1" required value="100"></label>
    <label>По вертикали: <input name="h" type="number" min="1" required value="100"></label>
    <label><input type="checkbox" name="aspect" checked>Сохранять пропорции</label></fieldset>`, [['ok','ОК'],['cancel','Отмена']], f=>{
    const e=f.elements, percent=()=>e.mode.value==='percent';
    f.addEventListener('change',event=>{ if(event.target.name==='mode'){ e.w.value=percent()?100:w; e.h.value=percent()?100:h; } });
    function sync(horizontal) { if(!e.aspect.checked) return;
      const [from,to,ratio]=horizontal?[e.w,e.h,h/w]:[e.h,e.w,w/h];
      if(from.valueAsNumber>0) to.value=Math.max(1,Math.round(from.valueAsNumber*(percent()?1:ratio)));
    }
    e.w.oninput=()=>sync(true); e.h.oninput=()=>sync(false); e.aspect.onchange=()=>sync(true);
    return ()=>{const calc=(n,src)=>percent()?Math.max(1,Math.round(n*src/100)):n;
      const width=calc(e.w.valueAsNumber,w), height=calc(e.h.valueAsNumber,h); checkSize(width,height); return [width,height];};
  });
  return result?.data;
}
