// Язык интерфейса EN/RU и кнопка переворота камеры.
// Исходников фронта нет (только собранный Vue-бандл), поэтому переводим DOM
// поверх бандла: английский зашит в сборку, русский берем из /lang.json.
(function () {
  var DICT = {};   // en -> ru
  var R2E = {};    // ru -> en, обратный, строится сам
  var enPats = []; // скомпилированные шаблоны для en->ru
  var ruPats = [];
  var lang = 'en';
  try { lang = localStorage.getItem('lang') === 'ru' ? 'ru' : 'en'; } catch (e) {}
  // можно задать язык ссылкой: ?lang=ru, запомнится
  try {
    var m = /[?&]lang=(en|ru)(&|$)/.exec(location.search);
    if (m) {
      lang = m[1];
      localStorage.setItem('lang', lang);
    }
  } catch (e) {}
  var langBtn = null;
  var flipBtn = null;
  var flipOn = false;

  var FLIP = {
    en: ['Flip camera 180°', 'Camera flipped: 180°'],
    ru: ['Перевернуть камеру на 180°', 'Камера перевернута: 180°']
  };

  function byLenDesc(a, b) { return b.length - a.length; }

  // Ключ ищем только целым словом. Иначе короткое "up" подменится внутри
  // "support", а "left" внутри имени иконки. Границы - латиница и кириллица,
  // без lookbehind, чтобы работало и в старых Safari.
  function compile(keys) {
    return keys.map(function (k) {
      var esc = k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      return {
        key: k,
        re: new RegExp('(^|[^A-Za-z0-9\\u0400-\\u04FF])(' + esc + ')(?![A-Za-z0-9\\u0400-\\u04FF])', 'g')
      };
    });
  }

  function build(dict) {
    DICT = dict || {};
    R2E = {};
    for (var k in DICT) R2E[DICT[k]] = k;
    // от длинных ключей к коротким, чтобы "turn right" не разваливалось на "right"
    enPats = compile(Object.keys(DICT).sort(byLenDesc));
    ruPats = compile(Object.keys(R2E).sort(byLenDesc));
  }

  function apply(text, map, pats) {
    for (var i = 0; i < pats.length; i++) {
      if (text.indexOf(pats[i].key) === -1) continue;
      text = text.replace(pats[i].re, function (m, pre, body) { return pre + map[body]; });
    }
    return text;
  }

  function trNode(node) {
    var t = node.nodeValue;
    if (!t || !t.trim()) return;
    // Иконки не трогаем: их текст вроде mdi-arrow-up-thick рисуется шрифтом,
    // любая замена сломает глиф.
    var p = node.parentElement;
    if (p && p.closest && p.closest('.v-icon')) return;
    var out = lang === 'ru' ? apply(t, DICT, enPats) : apply(t, R2E, ruPats);
    if (out !== t) node.nodeValue = out;   // пишем только при реальном изменении, иначе зациклим observer
  }

  function trTree(root) {
    if (!root) return;
    if (root.nodeType === 3) { trNode(root); return; }
    if (root.nodeType !== 1) return;
    var w = document.createTreeWalker(root, 4 /* SHOW_TEXT */, null);
    var n;
    while ((n = w.nextNode())) trNode(n);
  }

  function trAll() { trTree(document.body); }

  function markLang() {
    if (!langBtn) return;
    var bs = langBtn.querySelectorAll('b');
    if (bs.length === 2) {
      bs[0].className = lang === 'en' ? 'on' : '';
      bs[1].className = lang === 'ru' ? 'on' : '';
    }
  }

  function makeLangBtn() {
    langBtn = document.createElement('button');
    langBtn.id = 'lang-btn';
    langBtn.type = 'button';
    langBtn.title = 'Переключить язык / Switch language';
    langBtn.innerHTML = '<b>EN</b><i>|</i><b>RU</b>';
    langBtn.addEventListener('click', function () {
      lang = lang === 'ru' ? 'en' : 'ru';
      try { localStorage.setItem('lang', lang); } catch (e) {}
      markLang();
      trAll();
      setFlipText();
    });
  }

  function ensureLangBtn() {
    // Шапка есть только при загруженных данных, поэтому ждем ее появления.
    var bar = document.querySelector('.appBar .v-toolbar__content') || document.querySelector('.appBar');
    if (!bar || !enPats.length) return;
    if (!langBtn) makeLangBtn();
    if (langBtn.parentElement !== bar) bar.appendChild(langBtn);
    markLang();
  }

  function setFlipText() {
    if (!flipBtn) return;
    var t = FLIP[lang];
    flipBtn.textContent = flipOn ? t[1] : t[0];
    flipBtn.classList.toggle('flip-on', flipOn);
  }

  function ensureFlipBtn() {
    var w = document.querySelector('.vedio-wrapper');
    if (!w) return;
    var sheet = w.closest ? w.closest('.mod-sheet') : null;
    if (!sheet) return;
    var wrap = sheet.querySelector('.mod-wrapper');
    if (!wrap) return;
    if (flipBtn && flipBtn.parentElement === sheet && flipBtn.previousElementSibling === wrap) return;
    if (!flipBtn) {
      flipBtn = document.createElement('button');
      flipBtn.id = 'cam-flip-btn';
      flipBtn.type = 'button';
      flipBtn.addEventListener('click', function () {
        fetch('/api/camera/flip', { method: 'POST' })
          .then(function (r) { return r.json(); })
          .then(function (d) { flipOn = !!d.flip; setFlipText(); });
      });
      fetch('/api/camera/flip')
        .then(function (r) { return r.json(); })
        .then(function (d) { flipOn = !!d.flip; setFlipText(); });
    }
    wrap.insertAdjacentElement('afterend', flipBtn);
    setFlipText();
  }

  function ensureAll() { ensureLangBtn(); ensureFlipBtn(); }

  function start() {
    ensureAll();
    trAll();
    var mo = new MutationObserver(function (muts) {
      for (var i = 0; i < muts.length; i++) {
        var m = muts[i];
        if (m.type === 'characterData') {
          trNode(m.target);
        } else {
          for (var j = 0; j < m.addedNodes.length; j++) trTree(m.addedNodes[j]);
        }
      }
      ensureAll(); // Vue мог пересобрать карточку видео или шапку
    });
    mo.observe(document.body, { childList: true, subtree: true, characterData: true });
  }

  fetch('lang.json')
    .then(function (r) { return r.json(); })
    .then(function (d) { build(d.ru || d); start(); })
    .catch(function () { build({}); start(); }); // без словаря кнопка языка не нужна, переворот работает
})();
