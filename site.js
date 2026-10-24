// Swarm Colosseum site script (design pass, 2026-10-10). Every page works without it: it
// only adds the theme button, ladder sorting, sizing for framed viewers, and the header's
// "now showing" line. It sets text, never HTML, because bot names come from bot files.
(function () {
  var root = document.documentElement;
  var base = root.getAttribute('data-root') || '';

  // theme: the system's choice until the visitor picks one; framed viewers follow it
  var btn = document.getElementById('theme');
  function current() {
    return root.dataset.theme ||
      (window.matchMedia && matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
  }
  function show() { if (btn) btn.textContent = 'Theme: ' + current(); }
  try { var saved = localStorage.getItem('sc-theme'); if (saved === 'light' || saved === 'dark') root.dataset.theme = saved; } catch (e) {}
  if (btn) {
    btn.hidden = false; show();
    btn.onclick = function () {
      var next = current() === 'light' ? 'dark' : 'light';
      root.dataset.theme = next; show();
      try { localStorage.setItem('sc-theme', next); } catch (e) {}
      document.querySelectorAll('iframe.viewer').forEach(function (f) {
        try { f.contentDocument.documentElement.dataset.theme = next; f.contentWindow.dispatchEvent(new Event('resize')); } catch (e) {}
      });
    };
  }

  // sortable ladder tables: <table data-sort>, one button per sortable header
  document.querySelectorAll('table[data-sort]').forEach(function (t) {
    var hs = t.querySelectorAll('th[data-k]');
    hs.forEach(function (th) {
      var b = th.querySelector('button'); if (!b) return;
      b.onclick = function () {
        var d = th.getAttribute('aria-sort') === 'descending' ? 'ascending' : 'descending';
        hs.forEach(function (h) { h.removeAttribute('aria-sort'); });
        th.setAttribute('aria-sort', d);
        var col = [].indexOf.call(th.parentNode.children, th), tb = t.tBodies[0];
        var rows = [].slice.call(tb.rows);
        rows.sort(function (a, b) {
          var x = a.cells[col].dataset.v || a.cells[col].textContent,
              y = b.cells[col].dataset.v || b.cells[col].textContent;
          var nx = parseFloat(x), ny = parseFloat(y);
          var c = isNaN(nx) || isNaN(ny) ? x.localeCompare(y) : nx - ny;
          return d === 'ascending' ? c : -c;
        });
        rows.forEach(function (r) { tb.appendChild(r); });
      };
    });
  });

  // a framed viewer reports its height; fit the frame to it (same origin only)
  window.addEventListener('message', function (ev) {
    if (ev.origin !== location.origin || !ev.data || ev.data.sc !== 'height') return;
    document.querySelectorAll('iframe.viewer.fit').forEach(function (f) {
      if (f.contentWindow === ev.source) f.style.height = Math.ceil(ev.data.h) + 'px';
    });
  });

  // the header's "now showing": the same schedule the home page's replay channel plays
  var who = document.querySelector('.live .who');
  if (who && window.fetch) {
    fetch(base + 'replays/channel.json').then(function (r) { return r.json(); }).then(function (ch) {
      var items = ch.items || [], total = 0;
      items.forEach(function (it) { total += it.frames * 60 + 3000; });
      if (!total) return;
      var off = ((Date.now() - Date.parse(ch.epoch)) % total + total) % total, k = 0;
      while (off >= items[k].frames * 60 + 3000) { off -= items[k].frames * 60 + 3000; k++; }
      who.textContent = items[k].a + ' v ' + items[k].d;
      who.parentNode.setAttribute('aria-label', 'Now showing a replay from night ' + ch.night +
        ': ' + items[k].a + ' versus ' + items[k].d);
    }).catch(function () {});
  }
})();
