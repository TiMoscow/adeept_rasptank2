/* Кнопка перезагрузки контейнера в шапке, сразу за кнопкой EN|RU.
   Исходников фронта нет (собранный Vue), поэтому кнопку и окна вешаем на
   DOM поверх бандла, как custom.js и lang.js.

   Как это работает: POST /api/system/restart гасит моторы и завершает
   процесс PID 1 через os._exit(0). Процесс умирает, политика
   restart: unless-stopped из docker-compose поднимает контейнер заново.
   Пока контейнер поднимается, висит оверлей, страница сама опрашивает
   сервер и делает reload, как только тот снова отвечает. */
(function () {
  'use strict';

  var I18N = {
    en: {
      btnTitle: 'Restart container',
      askTitle: 'Restart container',
      askText: 'The control container will restart. The robot will stop and the page will reload by itself once the container is back.',
      yes: 'Restart',
      no: 'Cancel',
      waitTitle: 'Container is restarting',
      waitText: 'The page will reload by itself when the robot is ready.',
      failText: 'The robot has not answered for a long time. It may not have restarted.',
      retry: 'Keep waiting',
      open: 'Reload page',
      badApi: 'The server does not support container restart'
    },
    ru: {
      btnTitle: 'Перезагрузить контейнер',
      askTitle: 'Перезагрузить контейнер',
      askText: 'Контейнер управления перезагрузится. Робот остановится, страница обновится сама, когда контейнер поднимется.',
      yes: 'Перезагрузить',
      no: 'Отмена',
      waitTitle: 'Контейнер перезагружается',
      waitText: 'Страница обновится сама, когда робот будет готов.',
      failText: 'Робот давно не отвечает. Возможно, он не перезагрузился.',
      retry: 'Продолжить ожидание',
      open: 'Обновить страницу',
      badApi: 'Сервер не поддерживает перезагрузку контейнера'
    }
  };

  var POLL_EVERY = 1500;   // период опроса, мс
  var GRACE = 2500;        // сколько молчим после ответа сервера: процесс умирает через 1с
  var DEADLINE = 120000;   // по прошествии этого времени считаем, что контейнер не поднялся

  var btn = null;
  var ask = null;
  var askText = null;
  var wait = null;
  var failBox = null;
  var pollTimer = null;
  var startedAt = 0;
  var scheduled = false;

  function curLang() {
    try { return window.localStorage.getItem('lang') === 'ru' ? 'ru' : 'en'; } catch (e) { return 'en'; }
  }

  function t(key) {
    var v = I18N[curLang()][key];
    return v === undefined ? key : v;
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

  function stopPoll() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }

  function showFail(text) {
    failBox.querySelector('.rw-err').textContent = text;
    wait.classList.add('rw-err-on');
  }

  // опрашиваем сервер, пока он не ответит после перезагрузки
  function startPoll() {
    stopPoll();
    startedAt = Date.now();
    wait.classList.remove('rw-err-on');
    pollTimer = setInterval(function () {
      if (Date.now() - startedAt < GRACE) { return; }
      fetch('/api/camera/flip')
        .then(function (r) {
          if (!r.ok) { return; }
          stopPoll();
          window.location.reload();
        })
        .catch(function () { /* контейнер еще не поднялся, ждем дальше */ });
      if (Date.now() - startedAt > DEADLINE) {
        stopPoll();
        showFail(t('failText'));
      }
    }, POLL_EVERY);
  }

  function startWait() {
    wait.classList.add('rw-on');
    startPoll();
  }

  function doRestart() {
    ask.style.display = 'none';
    startWait();
    fetch('/api/system/restart', { method: 'POST' })
      .then(function (r) {
        // сервер есть, но эндпоинта нет: не молчим, показываем ошибку
        if (!r.ok) { stopPoll(); showFail(t('badApi')); }
      })
      .catch(function () {
        // ответа не будет: сервер умирает сразу после приема запроса.
        // это нормально, опрос уже идет
      });
  }

  function buildAsk() {
    ask = el('div', {'class': 'pp-modal', id: 'restart-ask'});
    var box = el('div', {'class': 'pp-modal-box'});
    var head = el('div', {'class': 'pp-modal-head', text: t('askTitle')});
    askText = el('div', {'class': 'rs-text'});
    var foot = el('div', {'class': 'pp-foot'});
    var no = el('button', {type: 'button', 'class': 'pp-btn', text: t('no')});
    var yes = el('button', {type: 'button', 'class': 'pp-btn pp-ok', text: t('yes')});
    no.addEventListener('click', function () { ask.style.display = 'none'; });
    yes.addEventListener('click', doRestart);
    ask.addEventListener('click', function (e) { if (e.target === ask) { ask.style.display = 'none'; } });
    foot.appendChild(no);
    foot.appendChild(yes);
    box.appendChild(head);
    box.appendChild(askText);
    box.appendChild(foot);
    ask.appendChild(box);
    ask.style.display = 'none';
    document.body.appendChild(ask);
  }

  function buildWait() {
    wait = el('div', {id: 'restart-wait'}, [
      el('div', {'class': 'rw-spin'}),
      el('div', {'class': 'rw-title'}),
      el('div', {'class': 'rw-text'}),
      failBox = el('div', {'class': 'rw-fail'}, [
        el('div', {'class': 'rw-err'}),
        el('div', {'class': 'rw-btns'}, [
          el('button', {type: 'button', 'class': 'rw-btn'}),
          el('button', {type: 'button', 'class': 'rw-btn'})
        ])
      ])
    ]);
    var btns = failBox.querySelectorAll('.rw-btn');
    btns[0].addEventListener('click', function () { startPoll(); });
    btns[1].addEventListener('click', function () { window.location.reload(); });
    document.body.appendChild(wait);
  }

  // тексты пишем при каждом открытии окна, чтобы поймать смену языка
  function paintTexts() {
    if (ask) {
      ask.querySelector('.pp-modal-head').textContent = t('askTitle');
      askText.textContent = t('askText');
      var ab = ask.querySelectorAll('.pp-foot .pp-btn');
      ab[0].textContent = t('no');
      ab[1].textContent = t('yes');
    }
    if (wait) {
      wait.querySelector('.rw-title').textContent = t('waitTitle');
      wait.querySelector('.rw-text').textContent = t('waitText');
      var wb = wait.querySelectorAll('.rw-btn');
      wb[0].textContent = t('retry');
      wb[1].textContent = t('open');
    }
    if (btn) { btn.title = t('btnTitle'); }
  }

  function buildBtn() {
    btn = document.createElement('button');
    btn.id = 'restart-btn';
    btn.type = 'button';
    btn.innerHTML = '<span class="mdi mdi-restart"></span>';
    btn.addEventListener('click', function () {
      paintTexts();
      ask.style.display = 'flex';
    });
  }

  function ensure() {
    var bar = document.querySelector('.appBar .v-toolbar__content') || document.querySelector('.appBar');
    if (!bar) { return; }
    if (!ask) { buildAsk(); buildWait(); }
    if (!btn) { buildBtn(); }
    // кнопка языка должна быть слева от нашей. lang.js вставляет ее в конец
    // шапки, поэтому за ней надо следить и переставляться правее
    var lb = document.getElementById('lang-btn');
    if (lb && lb.parentElement === bar) {
      if (lb.nextElementSibling === btn) { return; }
      lb.insertAdjacentElement('afterend', btn);
    } else {
      if (btn === bar.lastElementChild) { return; }
      bar.appendChild(btn);
    }
    paintTexts();
  }

  function schedule() {
    if (scheduled) { return; }
    scheduled = setTimeout(function () { scheduled = null; ensure(); }, 50);
  }

  ensure();
  new MutationObserver(schedule).observe(document.body, {childList: true, subtree: true});
  // смена языка кнопкой EN|RU: перечитываем тексты на случай, если открыто окно
  setInterval(function () {
    if (document.querySelector('#restart-ask[style*="flex"]') ||
        document.querySelector('#restart-wait.rw-on')) {
      paintTexts();
    }
  }, 1000);
})();
