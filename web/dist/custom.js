/* Панель «Фото и съемка по расписанию» для веб-интерфейса RaspTank.
   Вставляется под кнопкой «180°», как и сама кнопка, через MutationObserver:
   фронтенд собран Vue, исходников у нас нет.

   Язык панели свой, на EN/RU. Следим за localStorage['lang'], который
   переключает lang.js, и пересобираем панель при смене языка. */
(function () {
  'use strict';

  var LS_DIR = 'rasptank.photo.dir';
  var LS_TL_DIR = 'rasptank.photo.tldir';

  var I18N = {
    en: {
      title: 'Photo',
      titleTl: 'Scheduled shooting',
      folder: 'Folder',
      every: 'Every',
      timeLimit: 'Time limit',
      choose: 'Choose folder…',
      takePhoto: 'Take photo',
      start: 'Start shooting',
      stop: 'Stop shooting',
      root: 'root',
      saveTo: 'Save to: ',
      photoFolder: '(photo folder)',
      noSubfolders: 'No subfolders',
      noConn: 'No connection to robot',
      shooting: 'Taking photo…',
      saved: 'Saved: ',
      shotFail: 'Failed to take photo',
      needFolder: 'Choose a folder to save photos first',
      needFolderTl: 'Choose a folder for the scheduled shooting first',
      errGeneric: 'Error',
      notSupported: 'Server does not support scheduled shooting',
      enterName: 'Enter a folder name',
      mkFail: 'Failed to create folder',
      current: 'Now: /',
      up: '.. up',
      createFolder: 'Create folder',
      cancel: 'Cancel',
      ok: 'OK',
      pickTitle: 'Where to save photos',
      namePh: 'new folder name',
      notRunning: 'Shooting is not running',
      stopped: 'Shooting stopped',
      recording: 'Recording: ',
      of: ' of ',
      everyX: ', every ',
      takenX: 'taken ',
      folderX: 'Folder: ',
      lastFrame: 'Last frame: ',
      errX: 'Error: ',
      freeX: 'Free: ',
      mb: ' MB',
      h: ' h',
      min: ' min',
      s: ' s',
      tIntTitle: 'interval between frames, HH:MM:SS',
      tDurTitle: 'how long to shoot, HH:MM:SS',
      reasons: {
        stopped: 'stopped manually',
        count: 'frame limit reached',
        duration: 'time limit reached',
        disk: 'not enough disk space',
        errors: 'too many consecutive errors'
      }
    },
    ru: {
      title: 'Фото',
      titleTl: 'Съемка по расписанию',
      folder: 'Папка',
      every: 'Каждые',
      timeLimit: 'Лимит по времени',
      choose: 'Выбрать папку…',
      takePhoto: 'Сделать фото',
      start: 'Запустить съемку',
      stop: 'Остановить съемку',
      root: 'корень',
      saveTo: 'Куда сохранять: ',
      photoFolder: '(папка фото)',
      noSubfolders: 'Вложенных папок нет',
      noConn: 'Нет связи с роботом',
      shooting: 'Снимаю…',
      saved: 'Сохранено: ',
      shotFail: 'Не удалось сделать фото',
      needFolder: 'Сначала выберите папку, куда сохранять фото',
      needFolderTl: 'Сначала выберите папку для автоматической съемки',
      errGeneric: 'Ошибка',
      notSupported: 'Сервер не поддерживает съемку по расписанию',
      enterName: 'Введите имя папки',
      mkFail: 'Не удалось создать папку',
      current: 'Сейчас: /',
      up: '.. наверх',
      createFolder: 'Создать папку',
      cancel: 'Отмена',
      ok: 'ОК',
      pickTitle: 'Куда сохранить фото',
      namePh: 'имя новой папки',
      notRunning: 'Съемка не запущена',
      stopped: 'Съемка остановлена',
      recording: 'Идет съемка: снято ',
      of: ' из ',
      everyX: ', каждые ',
      takenX: 'снято ',
      folderX: 'Папка: ',
      lastFrame: 'Последний кадр: ',
      errX: 'Ошибка: ',
      freeX: 'Свободно: ',
      mb: ' МБ',
      h: ' ч',
      min: ' мин',
      s: ' с',
      tIntTitle: 'промежуток между кадрами, ЧЧ:ММ:СС',
      tDurTitle: 'сколько снимать, ЧЧ:ММ:СС',
      reasons: {
        stopped: 'остановлена вручную',
        count: 'достигнут лимит кадров',
        duration: 'вышло заданное время',
        disk: 'мало места на диске',
        errors: 'слишком много ошибок подряд'
      }
    }
  };

  var panel = null;
  var els = {};
  var running = false;
  var configLoaded = false;
  var scheduled = null;
  var picker = null;     // окно выбора папки
  var pickerDir = '';    // текущая папка внутри окна
  var pickerTarget = 'manual';  // для чего открыто окно: manual | tl
  var langCache = null;

  function curLang() {
    try { return window.localStorage.getItem('lang') === 'ru' ? 'ru' : 'en'; } catch (e) { return 'en'; }
  }

  function t(key) {
    var v = I18N[curLang()][key];
    return v === undefined ? key : v;
  }

  function tR(key) {
    return I18N[curLang()].reasons[key] || '';
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

  function row(label, controls) {
    return el('div', {'class': 'pp-row'}, [el('span', {text: label})].concat(controls));
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

  function lsGet(key) {
    try { return window.localStorage.getItem(key) || ''; } catch (e) { return ''; }
  }
  function lsSet(key, value) {
    try { window.localStorage.setItem(key, value); } catch (e) { /* без хранилища тоже работает */ }
  }

  function setMsg(node, text, isError) {
    node.textContent = text;
    node.classList.toggle('pp-err', !!isError);
  }

  // перевод секунд в ЧЧ:ММ:СС для нативного пикера времени и обратно
  function toTime(sec) {
    var s = Math.max(0, Math.round(Number(sec) || 0));
    var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), ss = s % 60;
    function p(n) { return (n < 10 ? '0' : '') + n; }
    return p(h) + ':' + p(m) + ':' + p(ss);
  }

  function fromTime(v) {
    var p = String(v || '').split(':').map(function (x) { return parseInt(x, 10) || 0; });
    while (p.length < 3) { p.unshift(0); }
    return p[0] * 3600 + p[1] * 60 + (p[2] || 0);
  }

  function fmtDur(sec) {
    var s = Math.max(0, Math.round(Number(sec) || 0));
    var parts = [];
    var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), ss = s % 60;
    if (h) { parts.push(h + t('h')); }
    if (m) { parts.push(m + t('min')); }
    if (ss || !parts.length) { parts.push(ss + t('s')); }
    return parts.join(' ');
  }

  function updatePathHint() {
    var base = els.basePath || '';
    var d = (els.dir.value || '').trim().replace(/^\/+|\/+$/g, '');
    els.dirText.textContent = d || t('root');
    els.dirPath.textContent = t('saveTo') + (base ? (base + (d ? '/' + d : '')) : (d || t('photoFolder')));
    var tl = (els.tlDir.value || '').trim().replace(/^\/+|\/+$/g, '');
    els.tlDirText.textContent = tl || t('root');
    els.tlPath.textContent = t('saveTo') + (base ? (base + (tl ? '/' + tl : '')) : (tl || t('photoFolder')));
  }

  function render(s) {
    var wasRunning = running;
    running = !!s.running;
    els.tl.textContent = running ? t('stop') : t('start');
    els.tl.classList.toggle('pp-on', running);
    [els.interval, els.dur].forEach(function (n) { n.disabled = running; });
    els.tlPick.disabled = running;

    if (running && !wasRunning) {  // страницу открыли посреди съемки: форма показывает ее параметры
      els.tlDir.value = s.dir || '';
      els.interval.value = toTime(s.interval);
      els.dur.value = toTime(s.duration);
      updatePathHint();
    }

    var lines = [];
    if (running) {
      lines.push(t('recording') + s.taken + (s.max_count ? t('of') + s.max_count : '') +
                 t('everyX') + fmtDur(s.interval));
      lines.push(t('folderX') + (s.dir || t('root')));
    } else if (s.stop_reason) {
      lines.push(t('stopped') + ' (' + (tR(s.stop_reason) || s.stop_reason) + '), ' + t('takenX') + s.taken);
    } else {
      lines.push(t('notRunning'));
    }
    if (s.last_file) { lines.push(t('lastFrame') + s.last_file); }
    if (s.last_error) { lines.push(t('errX') + s.last_error); }
    if (s.free_mb !== null && s.free_mb !== undefined) { lines.push(t('freeX') + s.free_mb + t('mb')); }

    els.status.textContent = '';
    lines.forEach(function (txt) { els.status.appendChild(el('div', {text: txt})); });
    els.status.classList.toggle('pp-err', !!s.last_error);
  }

  function poll() {
    var l = curLang();
    if (l !== langCache) {
      langCache = l;
      rebuildPanel();
      return Promise.resolve();
    }
    return call('/api/timelapse/status').then(function (s) {
      if (s && s.running !== undefined) { render(s); }
    }).catch(function () { /* связи нет: оставляем прошлое состояние */ });
  }

  function loadConfig() {
    return call('/api/photo/config').then(function (c) {
      if (!c || !c.base) { return; }  // сервер без новых эндпоинтов
      els.basePath = c.base;
      if (!configLoaded) {
        configLoaded = true;
        var st = c.settings || {};
        if (!running) {
          els.dir.value = lsGet(LS_DIR) || st.dir || '';
          els.tlDir.value = lsGet(LS_TL_DIR) || st.dir || '';
          if (st.interval) {
            els.interval.value = toTime(st.interval);
            els.dur.value = toTime(st.duration);
          }
        }
      }
      updatePathHint();
    }).catch(function () {});
  }

  function onShot() {
    if (!els.dir.value.trim()) {
      setMsg(els.msg, t('needFolder'), true);
      return;
    }
    els.shot.disabled = true;
    setMsg(els.msg, t('shooting'), false);
    lsSet(LS_DIR, els.dir.value.trim());
    call('/api/photo', 'POST', {dir: els.dir.value.trim()}).then(function (d) {
      if (d.ok) {
        setMsg(els.msg, t('saved') + d.file, false);
        loadConfig();
      } else {
        setMsg(els.msg, d.error || t('shotFail'), true);
      }
    }).catch(function () {
      setMsg(els.msg, t('noConn'), true);
    }).then(function () {
      els.shot.disabled = false;
    });
  }

  function onTimelapse() {
    setMsg(els.err, '', false);
    if (!running && !els.tlDir.value.trim()) {
      setMsg(els.err, t('needFolderTl'), true);
      return;
    }
    els.tl.disabled = true;
    var req;
    if (running) {
      req = call('/api/timelapse/stop', 'POST', {});
    } else {
      var seconds = fromTime(els.interval.value);
      var durSeconds = fromTime(els.dur.value);
      lsSet(LS_TL_DIR, els.tlDir.value.trim());
      req = call('/api/timelapse/start', 'POST', {
        dir: els.tlDir.value.trim(),
        interval: seconds,
        max_count: 0,
        duration: durSeconds
      });
    }
    req.then(function (d) {
      if (d.ok === false) { setMsg(els.err, d.error || t('errGeneric'), true); }
      else if (d.ok === undefined) { setMsg(els.err, t('notSupported'), true); }
      return poll().then(loadConfig);
    }).catch(function () {
      setMsg(els.err, t('noConn'), true);
    }).then(function () {
      els.tl.disabled = false;
    });
  }

  // ---- окно выбора папки ----

  function openPicker(target) {
    pickerTarget = target || 'manual';
    pickerDir = (pickerTarget === 'tl' ? els.tlDir.value : els.dir.value).trim();
    els.newName.value = '';
    setMsg(els.pickerMsg, '', false);
    picker.style.display = 'flex';
    renderPicker();
  }

  function closePicker() {
    picker.style.display = 'none';
  }

  function buildPicker() {
    picker = el('div', {'class': 'pp-modal'});
    var box = el('div', {'class': 'pp-modal-box'});
    var head = el('div', {'class': 'pp-modal-head', text: t('pickTitle')});
    els.crumb = el('div', {'class': 'pp-crumb'});
    els.list = el('div', {'class': 'pp-list'});
    var newRow = el('div', {'class': 'pp-newrow'});
    els.newName = el('input', {type: 'text', placeholder: t('namePh'), maxlength: '64'});
    var mk = el('button', {type: 'button', 'class': 'pp-btn', text: t('createFolder')});
    els.pickerMsg = el('div', {'class': 'pp-msg'});
    var foot = el('div', {'class': 'pp-foot'});
    var cancel = el('button', {type: 'button', 'class': 'pp-btn', text: t('cancel')});
    var ok = el('button', {type: 'button', 'class': 'pp-btn pp-ok', text: t('ok')});

    mk.addEventListener('click', function () {
      var name = (els.newName.value || '').trim();
      if (!name) { setMsg(els.pickerMsg, t('enterName'), true); return; }
      var target = pickerDir ? (pickerDir + '/' + name) : name;
      call('/api/photo/mkdir', 'POST', {dir: target}).then(function (r) {
        if (r.ok) {
          els.newName.value = '';
          setMsg(els.pickerMsg, '', false);
          pickerDir = r.dir || '';
          renderPicker();
        } else {
          setMsg(els.pickerMsg, r.error || t('mkFail'), true);
        }
      }).catch(function () { setMsg(els.pickerMsg, t('noConn'), true); });
    });

    cancel.addEventListener('click', closePicker);
    ok.addEventListener('click', function () {
      if (pickerTarget === 'tl') {
        els.tlDir.value = pickerDir;
        lsSet(LS_TL_DIR, pickerDir);
      } else {
        els.dir.value = pickerDir;
        lsSet(LS_DIR, pickerDir);
      }
      updatePathHint();
      closePicker();
    });

    newRow.appendChild(els.newName);
    newRow.appendChild(mk);
    foot.appendChild(cancel);
    foot.appendChild(ok);
    box.appendChild(head);
    box.appendChild(els.crumb);
    box.appendChild(els.list);
    box.appendChild(newRow);
    box.appendChild(els.pickerMsg);
    box.appendChild(foot);
    picker.appendChild(box);
    picker.addEventListener('click', function (e) { if (e.target === picker) { closePicker(); } });
    document.body.appendChild(picker);
  }

  function renderPicker() {
    els.crumb.textContent = t('current') + (pickerDir || t('root'));
    els.list.textContent = '';
    if (pickerDir) {
      var up = el('button', {type: 'button', 'class': 'pp-item', text: t('up')});
      up.addEventListener('click', function () {
        var parts = pickerDir.split('/');
        parts.pop();
        pickerDir = parts.join('/');
        renderPicker();
      });
      els.list.appendChild(up);
    }
    call('/api/photo/folders?dir=' + encodeURIComponent(pickerDir)).then(function (r) {
      var items = (r && r.items) || [];
      if (!items.length) {
        els.list.appendChild(el('div', {'class': 'pp-empty', text: t('noSubfolders')}));
        return;
      }
      items.forEach(function (f) {
        var b = el('button', {type: 'button', 'class': 'pp-item', text: f.split('/').pop()});
        b.addEventListener('click', function () {
          pickerDir = f;
          renderPicker();
        });
        els.list.appendChild(b);
      });
    }).catch(function () {
      els.list.appendChild(el('div', {'class': 'pp-empty', text: t('noConn')}));
    });
  }

  // пересоздание панели: язык сменился, тексты строятся заново через t()
  function rebuildPanel() {
    if (picker) { picker.remove(); picker = null; }
    if (panel) { panel.remove(); panel = null; }
    running = false;
    configLoaded = false;
    build();
    ensure();
  }

  function build() {
    els.dir = el('input', {type: 'hidden', id: 'pp-dir'});
    els.dirText = el('div', {'class': 'pp-cur', text: t('root')});
    els.pick = el('button', {type: 'button', 'class': 'pp-btn pp-mini', text: t('choose')});
    els.dirPath = el('div', {'class': 'pp-path'});
    els.tlDir = el('input', {type: 'hidden', id: 'pp-tldir'});
    els.tlDirText = el('div', {'class': 'pp-cur', text: t('root')});
    els.tlPick = el('button', {type: 'button', 'class': 'pp-btn pp-mini', text: t('choose')});
    els.tlPath = el('div', {'class': 'pp-path'});
    els.shot = el('button', {type: 'button', 'class': 'pp-btn', text: t('takePhoto')});
    els.msg = el('div', {'class': 'pp-msg'});
    els.interval = el('input', {type: 'time', id: 'pp-interval', step: '1', value: '00:01:00', title: t('tIntTitle')});
    els.dur = el('input', {type: 'time', id: 'pp-dur', step: '1', value: '00:00:00', title: t('tDurTitle')});
    els.tl = el('button', {type: 'button', 'class': 'pp-btn', text: t('start')});
    els.err = el('div', {'class': 'pp-msg'});
    els.status = el('div', {'class': 'pp-status'});

    els.shot.addEventListener('click', onShot);
    els.tl.addEventListener('click', onTimelapse);
    els.pick.addEventListener('click', function () { openPicker('manual'); });
    els.tlPick.addEventListener('click', function () { openPicker('tl'); });

    buildPicker();

    panel = el('div', {id: 'photo-panel'}, [
      els.dir,
      els.tlDir,
      el('div', {'class': 'pp-title', text: t('title')}),
      row(t('folder'), [els.dirText, els.pick]),
      els.dirPath,
      els.shot,
      els.msg,
      el('div', {'class': 'pp-sep'}),
      el('div', {'class': 'pp-title', text: t('titleTl')}),
      row(t('folder'), [els.tlDirText, els.tlPick]),
      els.tlPath,
      row(t('every'), [els.interval]),
      row(t('timeLimit'), [els.dur]),
      els.tl,
      els.err,
      els.status
    ]);

    loadConfig();
    poll();
  }

  function ensure() {
    var video = document.querySelector('.vedio-wrapper');
    if (!video) { return; }
    var sheet = video.closest('.mod-sheet');
    if (!sheet) { return; }
    var anchor = sheet.querySelector('#cam-flip-btn') || sheet.querySelector('.mod-wrapper');
    if (!anchor) { return; }
    var l = curLang();
    if (langCache !== l) {
      langCache = l;
      if (picker) { picker.remove(); picker = null; }
      if (panel) { panel.remove(); panel = null; }
      configLoaded = false;
      running = false;
    }
    if (!panel) { build(); }
    if (panel.parentElement === sheet && panel.previousElementSibling === anchor) { return; }
    anchor.insertAdjacentElement('afterend', panel);
  }

  function schedule() {
    if (scheduled) { return; }
    scheduled = setTimeout(function () { scheduled = null; ensure(); }, 50);
  }

  ensure();
  new MutationObserver(schedule).observe(document.body, {childList: true, subtree: true});
  setInterval(function () {
    if (panel && panel.isConnected && !document.hidden) { poll(); }
  }, 2000);
})();