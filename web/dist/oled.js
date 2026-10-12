/* Панель «Дисплей»: эксклюзивные режимы OLED.
   Сверху переключатель режима (данные, глаза, радар, превью), выбран ровно
   один. Под ним настройки активного режима. Для данных это конструктор строк:
   порядок пунктов это порядок строк на экране, первый рисуется вверху.
   Вставляется под панелью фото через MutationObserver: фронтенд собран Vue,
   исходников у нас нет.

   Язык свой, на EN/RU. Следим за localStorage['lang'], который переключает
   lang.js, и пересобираем панель при смене языка. */
(function () {
  'use strict';

  var MAX = 8;   // высота экрана 64 пикселя, строка 8 пикселей

  var I18N = {
    en: {
      title: 'Display',
      modes: {data: 'Data', eyes: 'Eyes', radar: 'Radar'},
      hint: 'Pick values. Order here is the order of lines on the OLED.',
      add: 'Add',
      remove: 'Remove',
      empty: 'Nothing selected',
      all: 'All values are already added',
      full: 'Limit reached: 8 lines max',
      noConn: 'No connection to robot',
      soon: 'Coming soon',
      react: 'React to',
      reactCommand: 'Commands',
      reactObstacle: 'Obstacle',
      reactPerson: 'Person',
      batLow: 'Sad when battery below, %',
      sleepAfter: 'Sleep after idle, s',
      obstacleCm: 'Obstacle distance, cm',
      radarNote: 'Scans with the camera servo, only when the robot is standing still. Watch the OLED.'
    },
    ru: {
      title: 'Дисплей',
      modes: {data: 'Данные', eyes: 'Глаза', radar: 'Радар'},
      hint: 'Выбери значения. Порядок здесь это порядок строк на OLED.',
      add: 'Добавить',
      remove: 'Убрать',
      empty: 'Ничего не выбрано',
      all: 'Все значения уже добавлены',
      full: 'Достигнут лимит: максимум 8 строк',
      noConn: 'Нет связи с роботом',
      soon: 'Скоро',
      react: 'Реагировать на',
      reactCommand: 'Команды',
      reactObstacle: 'Препятствие',
      reactPerson: 'Человека',
      batLow: 'Грусть при заряде ниже, %',
      sleepAfter: 'Сон после простоя, с',
      obstacleCm: 'Дистанция препятствия, см',
      radarNote: 'Скан сервой камеры, только когда робот стоит. Смотри на OLED.'
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

  function modeLabel(key) {
    var m = I18N[curLang()].modes;
    return m[key] || key;
  }

  function el(tag, props, children) {
    var n = document.createElement(tag);
    Object.keys(props || {}).forEach(function (k) {
      if (k === 'text') { n.textContent = props[k]; }
      else if (k === 'class') { n.className = props[k]; }
      else if (k === 'checked' || k === 'disabled' || k === 'value') { n[k] = props[k]; }
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
    els.modes = el('div', {'class': 'od-modes'});
    els.body = el('div', {'class': 'od-body'});
    els.msg = el('div', {'class': 'od-msg'});

    panel = el('div', {id: 'oled-panel'}, [
      el('div', {'class': 'od-title', text: t('title')}),
      els.modes,
      els.body,
      els.msg
    ]);
    fetchStatus();
  }

  function render() {
    if (!data) { return; }
    renderModes();
    renderBody();
  }

  // --- переключатель режимов: выбор один, как радиокнопка ---

  function renderModes() {
    els.modes.textContent = '';
    (data.modes || []).forEach(function (m) {
      var b = el('button', {type: 'button', 'class': 'od-mode', text: modeLabel(m)});
      if (m === data.mode) { b.className += ' od-on'; }
      b.addEventListener('click', function () { onMode(m); });
      els.modes.appendChild(b);
    });
  }

  function onMode(mode) {
    if (!data || mode === data.mode) { return; }
    call('/api/oled/mode', 'POST', {mode: mode}).then(function (d) {
      if (d && d.mode) { data.mode = d.mode; render(); }
    }).catch(function () { setMsg(t('noConn'), true); });
  }

  // --- тело панели: настройки активного режима ---

  function renderBody() {
    els.body.textContent = '';
    if (data.mode === 'data') { buildDataBody(); }
    else if (data.mode === 'eyes') { buildEyesBody(); }
    else if (data.mode === 'radar') { els.body.appendChild(el('div', {'class': 'od-hint', text: t('radarNote')})); }
  }

  function buildDataBody() {
    els.select = el('select', {'class': 'od-select'});
    els.add = el('button', {type: 'button', 'class': 'od-add', text: t('add')});
    els.list = el('div', {'class': 'od-list'});
    els.add.addEventListener('click', onAdd);
    els.body.appendChild(el('div', {'class': 'od-hint', text: t('hint')}));
    els.body.appendChild(el('div', {'class': 'od-addrow'}, [els.select, els.add]));
    els.body.appendChild(els.list);
    renderItems();
  }

  function renderItems() {
    var items = data.items || [];
    var left = (data.available || []).filter(function (k) { return items.indexOf(k) === -1; });

    // выпадающий список: только то, чего еще нет. Выбор сохраняем
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
    if (!data || data.mode !== 'data' || !els.list) { return; }
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
    saveItems((data.items || []).concat([k]));
  }

  function onRemove(k) {
    if (!data) { return; }
    saveItems((data.items || []).filter(function (x) { return x !== k; }));
  }

  function saveItems(items) {
    setMsg('');
    call('/api/oled/items', 'POST', {items: items}).then(function (d) {
      if (d && d.items) {
        data.items = d.items;
        renderItems();
      }
    }).catch(function () {
      setMsg(t('noConn'), true);
    });
  }

  // --- настройки режима глаз ---

  function optNumber(key, lbl) {
    var inp = el('input', {type: 'number', 'class': 'od-num-in', value: String(data.options[key])});
    inp.addEventListener('change', function () {
      var v = parseInt(inp.value, 10);
      if (isNaN(v)) { inp.value = String(data.options[key]); return; }
      saveOptions(key, v);
    });
    return el('label', {'class': 'od-opt'}, [
      el('span', {'class': 'od-opt-name', text: lbl}),
      inp
    ]);
  }

  function optCheck(key, lbl) {
    var inp = el('input', {type: 'checkbox', checked: !!data.options[key]});
    inp.addEventListener('change', function () {
      saveOptions(key, !!inp.checked);
    });
    return el('label', {'class': 'od-opt od-opt-check'}, [inp, el('span', {text: lbl})]);
  }

  function buildEyesBody() {
    els.body.appendChild(optNumber('bat_low', t('batLow')));
    els.body.appendChild(optNumber('sleep_after', t('sleepAfter')));
    els.body.appendChild(optNumber('obstacle_cm', t('obstacleCm')));
    els.body.appendChild(el('div', {'class': 'od-sub', text: t('react')}));
    els.body.appendChild(optCheck('react_command', t('reactCommand')));
    els.body.appendChild(optCheck('react_obstacle', t('reactObstacle')));
    els.body.appendChild(optCheck('react_person', t('reactPerson')));
  }

  function saveOptions(key, value) {
    var patch = {};
    patch[key] = value;
    setMsg('');
    call('/api/oled/options', 'POST', {options: patch}).then(function (d) {
      if (d && d.options) { data.options = d.options; }
    }).catch(function () {
      setMsg(t('noConn'), true);
    });
  }

  function fetchStatus() {
    return call('/api/oled/status').then(function (d) {
      if (d && d.modes) {
        data = d;
        render();
      }
    }).catch(function () { /* связи нет: держим прошлое */ });
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
      if (!d || !d.modes) { return; }
      // режим сменили из другого окна: пересобираем целиком
      if (!data || d.mode !== data.mode) { data = d; render(); return; }
      data.values = d.values;
      data.items = d.items;
      renderValues();
    }).catch(function () {});
  }, 2000);
})();
