/* Порядок блоков: инструкция в самом конце страницы.
   Видео, управление и остальные блоки рисует Vue, порядок зашит в бандл,
   исходников у нас нет. Инструкция стоит в левой колонке рядом с видео, а ее
   просят в конец. Выносим в конец .controll-area тем же MutationObserver-приемом,
   каким панели фото и дисплея встают после сетки блоков.
   Итоговый порядок: сетка блоков -> Фото -> Дисплей -> Инструкция. */
(function () {
  'use strict';

  // заголовок модуля: EN зашит в сборку, RU подставляет lang.js
  var TITLE_EN = 'Instruction';
  var TITLE_RU = 'Инструкция';

  function find() {
    var sheets = document.querySelectorAll('.mod-sheet');
    for (var i = 0; i < sheets.length; i++) {
      var name = sheets[i].querySelector('.mod-name');
      if (!name) { continue; }
      var txt = (name.textContent || '').trim();
      if (txt === TITLE_EN || txt === TITLE_RU) {
        return sheets[i].closest ? sheets[i].closest('.col') : null;
      }
    }
    return null;
  }

  function ensure() {
    var area = document.querySelector('.controll-area');
    if (!area) { return; }
    var col = find();
    if (!col) { return; }
    // уже последний блок страницы — не трогаем, иначе уйдем в цикл перестановок
    if (col.parentElement === area && !col.nextElementSibling) { return; }
    area.appendChild(col);
  }

  var scheduled = null;
  function schedule() {
    if (scheduled) { return; }
    scheduled = setTimeout(function () { scheduled = null; ensure(); }, 50);
  }

  ensure();
  new MutationObserver(schedule).observe(document.body, { childList: true, subtree: true });
})();
