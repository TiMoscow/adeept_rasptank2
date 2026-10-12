/* Панель «Дисплей»: конструктор строк OLED.
   Сверху выпадающий список доступных значений, под ним выбранные по порядку.
   Порядок выбранных это порядок строк на дисплее, первый пункт рисуется вверху.
   Крестик убирает пункт. Вставляется под панелью фото через MutationObserver:
   фронтенд собран Vue, исходников у нас нет.

   Язык свой, на EN/RU. Следим за localStorage['lang'], который переключает
   lang.js, и пересобираем панель при смене языка. */
(function () {
  'use strict';

  var MAX = 8;   // высота экрана 64 пикселя, строка 8 пикселей

  var I18N = {
    en: {
      title: 'Display',
      hint: 'Pick values. Order here is the order of lines on the OLED.',
      add: 'Add',
      remove: 'Remove',
      empty: 'Nothing selected',
      all: 'All values are already added',
      full: 'Limit reached: 8 lines max',
      noConn: 'No connection to robot'
    },
    ru: {
      title: 'Дисплей',
      hint: 'Выбери значения. Порядок здесь это порядок строк на OLED.',
      add: 'Добавить',
      remove: 'Убрать',
      empty: 'Ничего не выбрано',
      all: 'Все значения уже добавлены',
      full: 'Достигнут лимит: максимум 8 строк',
      noConn: 'Нет связи с роботом'
    }
  };

  var LABELS = {
    en: {time: 'Time', date: 'Date', temp: 'CPU temp', mem: 'Memory', cpu: 'CPU load', battery: 'Battery', uptime: 'Uptime'},
    ru: {time: 'Время', date: 'Дата', temp: 'Температура CPU', mem: 'Память', cpu: 'Загрузка CPU', battery: 'Батарея', uptime: 'Uptime'}
  };

  var panel = null;
  var els = {};
  var data = null;       // последний ответ сервера
  var langCache = null;

  function curLang() {
    try { return window.localStorage.getItem('lang') === 'ru' ? 'ru' : 'en'; } catch (e) { return 'en'; }
  }

  function t(key) {
    var v = I18N[curLang()][key];
    return v === undefined ? key : v;
  }

  function label(key) {
    return LABELS[curLang()][key] || key;
  }

  function el(tag, props, children) {
    var n = document.createElement(tag);
    Object.keys(props || {}).forEach(function (k) {
      if (k === 'text') { n.textContent = props[k]; }
      else if (k === 'class') { n.className = props[k]; }
      else { n.setAttribute(k, props[k]); }
    });
    (children || []).forEach(function (c) { n.appendChild(c); });
    return n;
  }

  function call(path, method, body) {
    var opts = {method: method || 'GET'};
    if (body) {
      opts.headers = {'Content-Type': 'application/json'};
      opts.body = JSON.stringify(body);
    }
    return fetch(path, opts).then(function (r) {
      return r.json().catch(function () { return {}; });
    });
  }

  function setMsg(text, isError) {
    els.msg.textContent = text || '';
    els.msg.classList.toggle('od-err', !!isError);
  }

  function build() {
    els.select = el('select', {'class': 'od-select'});
    els.add = el('button', {type: 'button', 'class': 'od-add', text: t('add')});
    els.list = el('div', {'class': 'od-list'});
    els.msg = el('div', {'class': 'od-msg'});
    els.add.addEventListener('click', onAdd);

    panel = el('div', {id: 'oled-panel'}, [
      el('div', {'class': 'od-title', text: t('title')}),
      el('div', {'class': 'od-hint', text: t('hint')}),
      el('div', {'class': 'od-addrow'}, [els.select, els.add]),
      els.list,
      els.msg
    ]);
    fetchStatus();
  }

  function render() {
    if (!data) { return; }
    var items = data.items || [];
    var left = (data.available || []).filter(function (k) { return items.indexOf(k) === -1; });

    // выпадающий список: только то, чего еще нет. Выбор пользователя сохраняем
    var prev = els.select.value;
    els.select.textContent = '';
    if (!left.length) {
      els.select.appendChild(el('option', {value: '', text: t('all')}));
      els.select.disabled = true;
      els.add.disabled = true;
    } else {
      left.forEach(function (k) {
        els.select.appendChild(el('option', {value: k, text: label(k)}));
      });
      els.select.disabled = false;
      els.add.disabled = items.length >= MAX;
      if (prev && left.indexOf(prev) !== -1) { els.select.value = prev; }
    }

    // список выбранных строк
    els.list.textContent = '';
    if (!items.length) {
      els.list.appendChild(el('div', {'class': 'od-empty', text: t('empty')}));
      return;
    }
    items.forEach(function (k, i) {
      var x = el('button', {type: 'button', 'class': 'od-x', text: '\u00d7', title: t('remove')});
      x.addEventListener('click', function () { onRemove(k); });
      els.list.appendChild(el('div', {'class': 'od-row'}, [
        el('span', {'class': 'od-num', text: String(i + 1)}),
        el('span', {'class': 'od-name', text: label(k)}),
        el('span', {'class': 'od-val', text: valueOf(k)}),
        x
      ]));
    });
  }

  function valueOf(k) {
    var v = data && data.values ? data.values[k] : undefined;
    return v === undefined ? '--' : v;
  }

  // только тексты значений, без перестройки списка: иначе select сбрасывается
  function renderValues() {
    if (!data || !panel) { return; }
    var rows = els.list.querySelectorAll('.od-row');
    var items = data.items || [];
    for (var i = 0; i < rows.length && i < items.length; i++) {
      var cell = rows[i].querySelector('.od-val');
      if (cell) { cell.textContent = valueOf(items[i]); }
    }
  }

  function onAdd() {
    if (!data) { return; }
    var k = els.select.value;
    if (!k) { return; }
    if ((data.items || []).length >= MAX) { setMsg(t('full'), true); return; }
    save((data.items || []).concat([k]));
  }

  function onRemove(k) {
    if (!data) { return; }
    save((data.items || []).filter(function (x) { return x !== k; }));
  }

  function save(items) {
    setMsg('');
    els.add.disabled = true;
    call('/api/oled/items', 'POST', {items: items}).then(function (d) {
      if (d && d.items) {
        data.items = d.items;
        render();
      }
    }).catch(function () {
      setMsg(t('noConn'), true);
    }).then(function () {
      render();
    });
  }

  function fetchStatus() {
    return call('/api/oled/status').then(function (d) {
      if (d && d.items) {
        data = d;
        render();
      }
    }).catch(function () { /* связи нет: держим прошлое */ });
  }

  function rebuild() {
    if (panel) { panel.remove(); panel = null; }
    data = null;
    build();
    ensure();
  }

  function ensure() {
    var video = document.querySelector('.vedio-wrapper');
    if (!video) { return; }
    var sheet = video.closest ? video.closest('.mod-sheet') : null;
    if (!sheet) { return; }
    // сидим под панелью фото, иначе под кнопкой переворота
    var anchor = sheet.querySelector('#photo-panel') ||
                 sheet.querySelector('#cam-flip-btn') ||
                 sheet.querySelector('.mod-wrapper');
    if (!anchor) { return; }

    var l = curLang();
    if (langCache !== l) {
      langCache = l;
      if (panel) { panel.remove(); panel = null; }
      data = null;
    }
    if (!panel) { build(); }
    if (panel.parentElement === sheet && panel.previousElementSibling === anchor) { return; }
    anchor.insertAdjacentElement('afterend', panel);
  }

  var scheduled = null;
  function schedule() {
    if (scheduled) { return; }
    scheduled = setTimeout(function () { scheduled = null; ensure(); }, 50);
  }

  ensure();
  new MutationObserver(schedule).observe(document.body, {childList: true, subtree: true});
  setInterval(function () {
    if (!panel || !panel.isConnected || document.hidden) { return; }
    call('/api/oled/status').then(function (d) {
      if (d && d.items) { data = d; renderValues(); }
    }).catch(function () {});
  }, 2000);
})();
