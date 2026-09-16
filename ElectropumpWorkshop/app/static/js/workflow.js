/* Process designer and process monitor — one drawing, two uses.
 *
 * The designer draws a map: nodes of six standard shapes, arrows between them,
 * a condition on each arrow, and people attached to each node. Nothing here
 * knows what any particular process is about; every label on the screen comes
 * from the server, and every change is a row.
 *
 * The monitor paints a run onto that same map, so whoever is watching sees
 * exactly the picture the admin drew, with the path it has taken marked on it.
 */
(function () {
  'use strict';
  var App = window.App;
  var esc = App.esc;

  /* A *surface* is one drawing on one set of elements: the designer's canvas,
   * or the monitor's read-only copy. Both are drawn by the same code, which is
   * the whole point — what the admin drew is what the watcher sees. */
  function surface(ids, editable) {
    return {
      ids: ids, editable: editable,
      graph: { nodes: [], edges: [] },
      live: null,                       // instance state, when watching a run
      zoom: 1, panX: 40, panY: 20
    };
  }

  var S = {
    data: null,            // the /definition payload
    workflowId: null,
    design: surface({ canvas: 'wf-canvas', plane: 'wf-plane', nodes: 'wf-nodes',
      edges: 'wf-edges', minimap: 'wf-minimap-canvas' }, true),
    mon: surface({ canvas: 'mon-canvas', plane: 'mon-plane', nodes: 'mon-nodes',
      edges: 'mon-edges' }, false),
    selection: null,       // {kind:'node'|'edge', id} — designer only
    connectFrom: null,
    connecting: false,
    dirtyLayout: false,
    monitor: { rows: [], selected: null }
  };

  var MIN_ZOOM = 0.25, MAX_ZOOM = 2.2;

  function part(surf, name) { return document.getElementById(surf.ids[name]); }

  /* ── boot ─────────────────────────────────────────────────────────── */
  document.addEventListener('DOMContentLoaded', function () {
    bindChrome();
    load();
  });

  function bindChrome() {
    var design = document.getElementById('pane-design');
    var monitor = document.getElementById('pane-monitor');
    document.getElementById('tab-design').onclick = function () {
      design.classList.remove('hidden'); monitor.classList.add('hidden');
      draw(S.design);
    };
    document.getElementById('tab-monitor').onclick = function () {
      monitor.classList.remove('hidden'); design.classList.add('hidden');
      loadInstances();
    };
    document.getElementById('zoom-in').onclick = function () { zoomBy(S.design, 1.2); };
    document.getElementById('zoom-out').onclick = function () { zoomBy(S.design, 1 / 1.2); };
    document.getElementById('zoom-fit').onclick = function () { fitToScreen(S.design); };
    document.getElementById('zoom-center').onclick = function () { centerMap(S.design); };
    document.getElementById('wf-save-layout').onclick = saveLayout;
    document.getElementById('wf-connect').onclick = toggleConnect;
    document.getElementById('wf-template').onchange = function () {
      S.workflowId = Number(this.value) || null;
      load(S.workflowId);
    };
    document.getElementById('wf-save-template').onclick = saveTemplate;
    document.getElementById('wf-new-version').onclick = newVersion;
    document.getElementById('wf-new-template').onclick = newTemplate;
    document.getElementById('wf-delete-template').onclick = deleteTemplate;
    document.getElementById('pal-search').oninput = App.debounce(renderPalette, 150);
    document.getElementById('mon-refresh').onclick = loadInstances;
    document.getElementById('mon-status').onchange = loadInstances;
    document.getElementById('mon-workflow').onchange = loadInstances;
    bindCanvas();
    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape' && S.connecting) toggleConnect();
      if (ev.key === 'Delete' && S.selection) removeSelected();
    });
  }

  function alertBox(message, kind) {
    var box = document.getElementById('wf-alert');
    if (!message) { box.innerHTML = ''; return; }
    box.innerHTML = '<div class="alert ' + (kind || 'info') + '">' +
      esc(message) + '</div>';
  }

  /* ── loading ──────────────────────────────────────────────────────── */
  async function load(workflowId) {
    try {
      var url = '/api/workflow/definition' +
        (workflowId ? '?workflow_id=' + workflowId : '');
      var res = await App.api.get(url);
      S.data = res.data;
      S.design.graph = res.data.graph || { nodes: [], edges: [] };
      S.workflowId = res.data.workflow.id;
      S.selection = null;
      renderTemplateBar();
      renderNodePalette();
      renderPalette();
      renderLegend();
      draw(S.design);
      fitToScreen(S.design);
      renderProps();
    } catch (err) {
      alertBox(err.message || 'نقشه فرایند بارگذاری نشد.', 'error');
    }
  }

  function mayEdit() { return !!(S.data && S.data.may_edit); }

  function renderTemplateBar() {
    var wf = S.data.workflow;
    document.getElementById('wf-name').textContent =
      wf.name + ' — نسخه ' + wf.version + ' · ' + wf.status_label +
      (wf.is_active ? ' · فعال' : '');
    var select = document.getElementById('wf-template');
    select.innerHTML = S.data.templates.map(function (t) {
      return '<option value="' + t.id + '"' +
        (t.id === wf.id ? ' selected' : '') + '>' + esc(t.name) +
        ' — نسخه ' + t.version + (t.is_active ? ' (فعال)' : '') + '</option>';
    }).join('');
    var status = document.getElementById('wf-status');
    status.innerHTML = S.data.template_status.map(function (s) {
      return '<option value="' + s.value + '"' +
        (s.value === wf.status ? ' selected' : '') + '>' + esc(s.label) +
        '</option>';
    }).join('');
    document.getElementById('wf-active').checked = !!wf.is_active;

    var note = document.getElementById('wf-running-note');
    if (S.data.running) {
      note.classList.remove('hidden');
      note.innerHTML = '⚠ <b>' + S.data.running + '</b> فرایند روی همین نسخه ' +
        'در جریان است. آن‌ها با تصویری از نقشه‌ی زمان شروع خود کار می‌کنند، ' +
        'پس تغییر این نقشه مسیرشان را عوض نمی‌کند؛ اگر می‌خواهید نقشه‌ی قدیم ' +
        'هم خوانا بماند، «نسخه جدید» بسازید.';
    } else {
      note.classList.add('hidden');
    }
    document.querySelectorAll('.wf-topbar-actions button, #wf-connect')
      .forEach(function (b) { b.disabled = !mayEdit(); });
  }

  function renderLegend() {
    document.getElementById('wf-legend').innerHTML = [
      ['#c3ced6', 'در انتظار'], ['#1e6fa5', 'در جریان'],
      ['#27ae60', 'انجام شده'], ['#f39c12', 'منتظر تأیید'],
      ['#c0392b', 'ردشده']
    ].map(function (p) {
      return '<span><i style="background:' + p[0] + '"></i>' + p[1] + '</span>';
    }).join('');
  }

  function renderNodePalette() {
    var box = document.getElementById('wf-node-palette');
    box.innerHTML = S.data.node_types.map(function (t) {
      return '<button class="wf-shape" type="button" data-type="' + t.value + '">' +
        '<span class="glyph">' + esc(t.icon || '▭') + '</span>' +
        '<span>' + esc(t.label) + '</span></button>';
    }).join('');
    box.querySelectorAll('.wf-shape').forEach(function (btn) {
      btn.onclick = function () { addNode(btn.dataset.type); };
      btn.disabled = !mayEdit();
    });
  }

  function renderPalette() {
    var term = (document.getElementById('pal-search').value || '').trim();
    function match(item) {
      return !term || (item.title || '').indexOf(term) >= 0 ||
        (item.code || '').indexOf(term) >= 0;
    }
    var sections = S.data.palette.sections.filter(match);
    var fields = S.data.palette.fields.filter(match);
    document.getElementById('pal-sections').innerHTML = sections.map(function (s) {
      return paletteItem('section', s.id, (s.icon || '▦') + ' ' + s.title,
        s.field_count + ' فیلد');
    }).join('') || '<p class="hint">موردی نیست.</p>';
    document.getElementById('pal-fields').innerHTML = fields.map(function (f) {
      return paletteItem('field', f.id, f.title, f.section_title || '');
    }).join('') || '<p class="hint">موردی نیست.</p>';
    document.querySelectorAll('.pal-item').forEach(function (node) {
      node.draggable = true;
      node.ondragstart = function (ev) {
        ev.dataTransfer.setData('text/plain', JSON.stringify({
          kind: node.dataset.kind, id: Number(node.dataset.id),
          title: node.dataset.title
        }));
      };
    });
  }

  function paletteItem(kind, id, title, meta) {
    return '<div class="pal-item small" data-kind="' + kind + '" data-id="' + id +
      '" data-title="' + esc(title) + '">' + esc(title) +
      (meta ? '<span class="pal-meta">' + esc(meta) + '</span>' : '') + '</div>';
  }

  /* ── drawing the map ──────────────────────────────────────────────── */
  function nodeById(surf, id) {
    return surf.graph.nodes.filter(function (n) { return n.id === id; })[0];
  }
  function nodeByKey(surf, key) {
    return surf.graph.nodes.filter(function (n) { return n.key === key; })[0];
  }
  function edgeById(surf, id) {
    return surf.graph.edges.filter(function (e) { return e.id === id; })[0];
  }

  function draw(surf) {
    if (!part(surf, 'nodes')) return;
    drawNodes(surf);
    drawEdges(surf);
    applyTransform(surf);
    drawMiniMap(surf);
  }

  function drawNodes(surf) {
    var host = part(surf, 'nodes');
    host.innerHTML = '';
    surf.graph.nodes.forEach(function (node) {
      host.appendChild(nodeElement(surf, node));
    });
  }

  function stateOf(surf, node) {
    if (!surf.live) return null;
    return (surf.live.nodes || []).filter(function (n) {
      return n.key === node.key;
    })[0] || null;
  }

  function nodeElement(surf, node) {
    var live = stateOf(surf, node);
    var selected = surf.editable && S.selection &&
      S.selection.kind === 'node' && S.selection.id === node.id;
    var box = document.createElement('div');
    box.className = 'wf-node type-' + node.type +
      (live ? ' state-' + live.state : '') + (selected ? ' selected' : '');
    // An end shape is red while the run is unfinished and green once it is.
    if (node.type === 'end' && live && live.status === 'submitted') {
      box.classList.add('finished');
    }
    box.style.left = (node.x || 0) + 'px';
    box.style.top = (node.y || 0) + 'px';
    box.style.width = (node.width || 200) + 'px';
    box.style.height = (node.height || 90) + 'px';
    box.dataset.id = node.id;

    var typeLabel = (S.data ? S.data.node_types : []).filter(function (t) {
      return t.value === node.type;
    })[0];
    var who = (node.principals || []).filter(function (p) {
      return p.role === 'assignee';
    }).map(function (p) { return p.name || p.user_name; }).join('، ');
    var approvers = (node.principals || []).filter(function (p) {
      return p.role === 'approver';
    }).length;

    box.innerHTML =
      '<span class="n-type">' + esc((typeLabel && typeLabel.label) || node.type) +
      '</span>' +
      (live ? '<span class="n-badge">' + esc(live.status_label || '') + '</span>'
        : (approvers ? '<span class="n-badge">' + approvers + ' تأییدکننده</span>'
          : '')) +
      '<span class="n-title">' + esc(node.icon || '') + ' ' + esc(node.title) +
      '</span>' +
      (who ? '<span class="n-who">👤 ' + esc(who) + '</span>'
        : (node.type === 'phase' || node.type === 'start'
          ? '<span class="n-who">بدون متولی</span>' : '')) +
      (surf.editable && mayEdit() ? '<span class="n-resize"></span>' : '');

    if (surf.editable) {
      box.addEventListener('pointerdown', function (ev) {
        if (ev.target.classList.contains('n-resize')) startResize(surf, ev, node, box);
        else startDrag(surf, ev, node, box);
      });
      box.addEventListener('click', function (ev) {
        ev.stopPropagation();
        if (S.connecting) { pickForConnect(node); return; }
        select('node', node.id);
      });
    } else if (live) {
      box.title = (live.status_label || '') +
        (live.waiting_on && live.waiting_on.length
          ? ' — منتظر: ' + live.waiting_on.join('، ') : '');
    }
    return box;
  }

  function edgePath(from, to) {
    var x1 = (from.x || 0) + (from.width || 200) / 2;
    var y1 = (from.y || 0) + (from.height || 90) / 2;
    var x2 = (to.x || 0) + (to.width || 200) / 2;
    var y2 = (to.y || 0) + (to.height || 90) / 2;
    // Leave the boxes at their edges rather than their centres, so an arrow
    // touches the shape instead of disappearing behind it.
    var a = trimToBox(x1, y1, x2, y2, from);
    var b = trimToBox(x2, y2, x1, y1, to);
    var curve = Math.min(140, Math.max(40, Math.abs(b.x - a.x) / 2));
    return {
      d: 'M' + a.x + ',' + a.y + ' C' + (a.x + (b.x > a.x ? curve : -curve)) +
        ',' + a.y + ' ' + (b.x - (b.x > a.x ? curve : -curve)) + ',' + b.y +
        ' ' + b.x + ',' + b.y,
      mid: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 - 8 }
    };
  }

  function trimToBox(cx, cy, ox, oy, node) {
    var hw = (node.width || 200) / 2 + 6, hh = (node.height || 90) / 2 + 6;
    var dx = ox - cx, dy = oy - cy;
    if (!dx && !dy) return { x: cx, y: cy };
    var scale = Math.min(
      dx ? hw / Math.abs(dx) : Infinity,
      dy ? hh / Math.abs(dy) : Infinity);
    return { x: cx + dx * scale, y: cy + dy * scale };
  }

  function drawEdges(surf) {
    var svg = part(surf, 'edges');
    var live = surf.live ? surf.live.edges || [] : [];
    var suffix = surf.ids.edges;      // markers must be unique per surface
    var parts = ['<defs>' +
      arrowMarker('arrow-' + suffix, '#8fa3b0') +
      arrowMarker('arrowok-' + suffix, '#27ae60') +
      arrowMarker('arrowno-' + suffix, '#c0392b') +
      arrowMarker('arrowon-' + suffix, '#1e6fa5') + '</defs>'];
    surf.graph.edges.forEach(function (edge) {
      var from = nodeByKey(surf, edge.source_key || edge.source);
      var to = nodeByKey(surf, edge.target_key || edge.target);
      if (!from || !to) return;
      var geom = edgePath(from, to);
      var state = live.filter(function (e) { return e.id === edge.id; })[0];
      var classes = ['wf-edge', 'kind-' + (edge.kind || 'default')];
      var marker = 'arrow-' + suffix;
      if (edge.kind === 'approved') marker = 'arrowok-' + suffix;
      if (edge.kind === 'rejected') marker = 'arrowno-' + suffix;
      if (state && state.taken) { classes.push('taken'); marker = 'arrowok-' + suffix; }
      if (state && state.active) { classes.push('active'); marker = 'arrowon-' + suffix; }
      if (surf.editable && S.selection && S.selection.kind === 'edge' &&
          S.selection.id === edge.id) {
        classes.push('selected');
      }
      if (surf.editable) {
        parts.push('<path class="wf-edge-hit" d="' + geom.d +
          '" data-edge="' + edge.id + '"></path>');
      }
      parts.push('<path class="' + classes.join(' ') + '" d="' + geom.d +
        '" marker-end="url(#' + marker + ')" data-edge="' + edge.id + '"></path>');
      var label = edge.label || edge.condition_label || '';
      if (label) {
        parts.push('<text class="wf-edge-label" text-anchor="middle" x="' +
          geom.mid.x + '" y="' + geom.mid.y + '">' +
          esc(label.length > 42 ? label.slice(0, 40) + '…' : label) + '</text>');
      }
    });
    svg.innerHTML = parts.join('');
    if (!surf.editable) return;
    svg.querySelectorAll('[data-edge]').forEach(function (path) {
      path.addEventListener('click', function (ev) {
        ev.stopPropagation();
        select('edge', Number(path.dataset.edge));
      });
    });
  }

  function arrowMarker(id, colour) {
    return '<marker id="' + id + '" viewBox="0 0 10 10" refX="9" refY="5" ' +
      'markerWidth="7" markerHeight="7" orient="auto-start-reverse">' +
      '<path d="M0,0 L10,5 L0,10 z" fill="' + colour + '"/></marker>';
  }

  /* ── pan, zoom, drag ──────────────────────────────────────────────── */
  function applyTransform(surf) {
    var plane = part(surf, 'plane');
    if (!plane) return;
    plane.style.transform = 'translate(' + surf.panX + 'px,' + surf.panY +
      'px) scale(' + surf.zoom + ')';
    if (surf.editable) {
      document.getElementById('zoom-label').textContent =
        Math.round(surf.zoom * 100).toLocaleString('fa-IR') + '٪';
    }
  }

  function zoomBy(surf, factor, originX, originY) {
    var canvas = part(surf, 'canvas');
    if (!canvas) return;
    var rect = canvas.getBoundingClientRect();
    var cx = originX === undefined ? rect.width / 2 : originX;
    var cy = originY === undefined ? rect.height / 2 : originY;
    var next = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, surf.zoom * factor));
    // Keep the point under the cursor where it is.
    surf.panX = cx - (cx - surf.panX) * (next / surf.zoom);
    surf.panY = cy - (cy - surf.panY) * (next / surf.zoom);
    surf.zoom = next;
    applyTransform(surf);
    drawMiniMap(surf);
  }

  function bounds(surf) {
    if (!surf.graph.nodes.length) return { x: 0, y: 0, w: 800, h: 500 };
    var xs = surf.graph.nodes.map(function (n) { return n.x || 0; });
    var ys = surf.graph.nodes.map(function (n) { return n.y || 0; });
    var xe = surf.graph.nodes.map(function (n) {
      return (n.x || 0) + (n.width || 200); });
    var ye = surf.graph.nodes.map(function (n) {
      return (n.y || 0) + (n.height || 90); });
    var x = Math.min.apply(null, xs), y = Math.min.apply(null, ys);
    return { x: x, y: y,
      w: Math.max.apply(null, xe) - x, h: Math.max.apply(null, ye) - y };
  }

  function fitToScreen(surf) {
    var canvas = part(surf, 'canvas');
    if (!canvas) return;
    var rect = canvas.getBoundingClientRect();
    var b = bounds(surf), pad = 40;
    var scale = Math.min((rect.width - pad * 2) / Math.max(b.w, 1),
      (rect.height - pad * 2) / Math.max(b.h, 1));
    surf.zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, scale));
    surf.panX = (rect.width - b.w * surf.zoom) / 2 - b.x * surf.zoom;
    surf.panY = (rect.height - b.h * surf.zoom) / 2 - b.y * surf.zoom;
    applyTransform(surf);
    drawMiniMap(surf);
  }

  function centerMap(surf) {
    var canvas = part(surf, 'canvas');
    if (!canvas) return;
    var rect = canvas.getBoundingClientRect();
    var b = bounds(surf);
    surf.panX = (rect.width - b.w * surf.zoom) / 2 - b.x * surf.zoom;
    surf.panY = (rect.height - b.h * surf.zoom) / 2 - b.y * surf.zoom;
    applyTransform(surf);
    drawMiniMap(surf);
  }

  function bindPan(surf) {
    var canvas = part(surf, 'canvas');
    if (!canvas || canvas.dataset.panBound) return;
    canvas.dataset.panBound = '1';
    var panning = false, startX = 0, startY = 0, originX = 0, originY = 0;
    canvas.addEventListener('pointerdown', function (ev) {
      // Anything with its own handling keeps the pointer. Capturing it here
      // would swallow the click that follows, and an arrow would never be
      // selectable with a real mouse.
      if (ev.target.closest('.wf-node') || ev.target.closest('.wf-minimap') ||
          ev.target.closest('[data-edge]')) return;
      panning = true;
      canvas.classList.add('panning');
      startX = ev.clientX; startY = ev.clientY;
      originX = surf.panX; originY = surf.panY;
      canvas.setPointerCapture(ev.pointerId);
    });
    canvas.addEventListener('pointermove', function (ev) {
      if (!panning) return;
      surf.panX = originX + (ev.clientX - startX);
      surf.panY = originY + (ev.clientY - startY);
      applyTransform(surf);
    });
    ['pointerup', 'pointercancel'].forEach(function (name) {
      canvas.addEventListener(name, function () {
        panning = false; canvas.classList.remove('panning'); drawMiniMap(surf);
      });
    });
    canvas.addEventListener('wheel', function (ev) {
      if (!ev.ctrlKey && !ev.metaKey) return;
      ev.preventDefault();
      var rect = canvas.getBoundingClientRect();
      zoomBy(surf, ev.deltaY < 0 ? 1.1 : 1 / 1.1,
        ev.clientX - rect.left, ev.clientY - rect.top);
    }, { passive: false });
    if (surf.editable) {
      canvas.addEventListener('click', function (ev) {
        if (ev.target.closest('.wf-node') || ev.target.closest('[data-edge]')) return;
        select(null);
      });
    }
  }

  function bindCanvas() { bindPan(S.design); }

  function startDrag(surf, ev, node, box) {
    if (!mayEdit() || S.connecting) return;
    ev.stopPropagation();
    box.setPointerCapture(ev.pointerId);
    var sx = ev.clientX, sy = ev.clientY;
    var ox = node.x || 0, oy = node.y || 0, moved = false;
    function move(e) {
      var dx = (e.clientX - sx) / surf.zoom, dy = (e.clientY - sy) / surf.zoom;
      if (Math.abs(dx) + Math.abs(dy) > 2) moved = true;
      node.x = Math.round((ox + dx) / 10) * 10;
      node.y = Math.round((oy + dy) / 10) * 10;
      box.style.left = node.x + 'px';
      box.style.top = node.y + 'px';
      drawEdges(surf);
    }
    function up() {
      box.removeEventListener('pointermove', move);
      box.removeEventListener('pointerup', up);
      if (moved) { markLayoutDirty(); drawMiniMap(surf); }
    }
    box.addEventListener('pointermove', move);
    box.addEventListener('pointerup', up);
  }

  function startResize(surf, ev, node, box) {
    if (!mayEdit()) return;
    ev.stopPropagation(); ev.preventDefault();
    box.setPointerCapture(ev.pointerId);
    var sx = ev.clientX, sy = ev.clientY;
    var ow = node.width || 200, oh = node.height || 90;
    function move(e) {
      node.width = Math.max(110,
        Math.round((ow + (e.clientX - sx) / surf.zoom) / 10) * 10);
      node.height = Math.max(64,
        Math.round((oh + (e.clientY - sy) / surf.zoom) / 10) * 10);
      box.style.width = node.width + 'px';
      box.style.height = node.height + 'px';
      drawEdges(surf);
    }
    function up() {
      box.removeEventListener('pointermove', move);
      box.removeEventListener('pointerup', up);
      markLayoutDirty();
    }
    box.addEventListener('pointermove', move);
    box.addEventListener('pointerup', up);
  }

  function markLayoutDirty() {
    S.dirtyLayout = true;
    var btn = document.getElementById('wf-save-layout');
    btn.textContent = '💾 ذخیره چیدمان •';
    btn.classList.add('btn-primary');
  }

  async function saveLayout() {
    try {
      await App.api.put('/api/workflow/map', {
        workflow_id: S.workflowId,
        nodes: S.design.graph.nodes.map(function (n) {
          return { id: n.id, x: n.x, y: n.y, width: n.width, height: n.height };
        }),
        canvas: { zoom: S.design.zoom, x: S.design.panX, y: S.design.panY }
      });
      S.dirtyLayout = false;
      var btn = document.getElementById('wf-save-layout');
      btn.textContent = '💾 ذخیره چیدمان';
      btn.classList.remove('btn-primary');
      App.toast('چیدمان نقشه ذخیره شد.', 'success');
    } catch (err) { App.toast(err.message, 'error'); }
  }

  /* ── the mini map ─────────────────────────────────────────────────── */
  function drawMiniMap(surf) {
    if (!surf.ids.minimap) return;
    var canvas = document.getElementById(surf.ids.minimap);
    var host = part(surf, 'canvas');
    if (!canvas || !host) return;
    var rect = canvas.getBoundingClientRect();
    if (!rect.width) return;
    canvas.width = rect.width; canvas.height = rect.height;
    var ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    var b = bounds(surf), pad = 6;
    var scale = Math.min((canvas.width - pad * 2) / Math.max(b.w, 1),
      (canvas.height - pad * 2) / Math.max(b.h, 1));
    function mx(x) { return pad + (x - b.x) * scale; }
    function my(y) { return pad + (y - b.y) * scale; }

    ctx.strokeStyle = '#c3ced6'; ctx.lineWidth = 1;
    surf.graph.edges.forEach(function (edge) {
      var from = nodeByKey(surf, edge.source_key || edge.source);
      var to = nodeByKey(surf, edge.target_key || edge.target);
      if (!from || !to) return;
      ctx.beginPath();
      ctx.moveTo(mx((from.x || 0) + (from.width || 200) / 2),
        my((from.y || 0) + (from.height || 90) / 2));
      ctx.lineTo(mx((to.x || 0) + (to.width || 200) / 2),
        my((to.y || 0) + (to.height || 90) / 2));
      ctx.stroke();
    });
    surf.graph.nodes.forEach(function (node) {
      var live = stateOf(surf, node);
      ctx.fillStyle = live ? miniColour(live.state) : '#1e6fa5';
      ctx.fillRect(mx(node.x || 0), my(node.y || 0),
        Math.max(3, (node.width || 200) * scale),
        Math.max(3, (node.height || 90) * scale));
    });
    var view = host.getBoundingClientRect();
    ctx.strokeStyle = '#e74c3c'; ctx.lineWidth = 1.5;
    ctx.strokeRect(mx((-surf.panX) / surf.zoom), my((-surf.panY) / surf.zoom),
      (view.width / surf.zoom) * scale, (view.height / surf.zoom) * scale);

    canvas.onclick = function (ev) {
      var r = canvas.getBoundingClientRect();
      var wx = b.x + (ev.clientX - r.left - pad) / scale;
      var wy = b.y + (ev.clientY - r.top - pad) / scale;
      surf.panX = view.width / 2 - wx * surf.zoom;
      surf.panY = view.height / 2 - wy * surf.zoom;
      applyTransform(surf); drawMiniMap(surf);
    };
  }

  function miniColour(state) {
    return ({ done: '#27ae60', approved: '#27ae60', active: '#1e6fa5',
      open: '#7fb3d8', awaiting_approval: '#f39c12', rejected: '#c0392b',
      skipped: '#dfe6eb' })[state] || '#c3ced6';
  }

  /* ── selection and properties ─────────────────────────────────────── */
  function select(kind, id) {
    S.selection = kind ? { kind: kind, id: id } : null;
    draw(S.design);
    renderProps();
  }

  function renderProps() {
    var host = document.getElementById('wf-props');
    var title = document.getElementById('wf-props-title');
    if (!S.selection) {
      title.textContent = 'ویژگی‌ها';
      host.innerHTML = '<p class="empty">یک گره یا پیکان را انتخاب کنید.</p>';
      return;
    }
    if (S.selection.kind === 'node') {
      var node = nodeById(S.design, S.selection.id);
      if (!node) { S.selection = null; return renderProps(); }
      title.textContent = 'ویژگی‌های گره';
      nodeProps(host, node);
    } else {
      var edge = edgeById(S.design, S.selection.id);
      if (!edge) { S.selection = null; return renderProps(); }
      title.textContent = 'ویژگی‌های پیکان';
      edgeProps(host, edge);
    }
  }

  function options(list, value, valueKey, labelKey) {
    return list.map(function (item) {
      var v = item[valueKey || 'value'];
      return '<option value="' + esc(v) + '"' +
        (String(v) === String(value) ? ' selected' : '') + '>' +
        esc(item[labelKey || 'label']) + '</option>';
    }).join('');
  }

  function nodeProps(host, node) {
    var cfg = node.config || {};
    var isApproval = node.type === 'approval';
    var isAction = node.type === 'action';
    var isStart = node.type === 'start';
    var html = [];

    html.push('<div class="prop-group">');
    html.push(row('عنوان', '<input id="p-title" value="' + esc(node.title) + '">'));
    html.push('<div class="prop-two">' +
      row('نوع گره', '<select id="p-type">' +
        options(S.data.node_types, node.type) + '</select>') +
      row('نماد', '<input id="p-icon" value="' + esc(node.icon || '') + '">') +
      '</div>');
    html.push(row('توضیح / راهنما',
      '<textarea id="p-desc" rows="3">' + esc(node.description || '') + '</textarea>'));
    html.push(row('شماره نمایش (ترتیب در فهرست‌ها)',
      '<input id="p-number" type="number" value="' +
      (node.stage_number == null ? '' : node.stage_number) + '">'));
    html.push('</div>');

    // people
    html.push('<div class="prop-group"><h4>افراد</h4>');
    S.data.principal_roles.forEach(function (role) {
      if (role.value === 'approver' && !isApproval) return;
      html.push('<div class="prop-row"><label>' + esc(role.label) + '</label>' +
        '<div class="prop-people" data-role="' + role.value + '">' +
        (node.principals || []).filter(function (p) {
          return p.role === role.value;
        }).map(function (p) {
          return '<span class="person-chip" data-kind="' +
            esc(p.principal_kind || 'user') + '" data-user="' + (p.user_id || '') +
            '" data-code="' + esc(p.role_code || '') + '">' +
            esc(p.name || p.user_name || p.role_code) +
            '<button type="button" class="p-remove">✕</button></span>';
        }).join('') +
        '<select class="p-add" data-role="' + role.value + '">' +
        '<option value="">➕ افزودن…</option>' +
        '<optgroup label="کاربران">' +
        S.data.users.map(function (u) {
          return '<option value="user:' + u.id + '">' + esc(u.full_name) + '</option>';
        }).join('') + '</optgroup>' +
        '<optgroup label="نقش‌ها (همه‌ی دارندگان)">' +
        S.data.roles.map(function (r) {
          return '<option value="role:' + r.value + '">' + esc(r.label) + '</option>';
        }).join('') + '</optgroup></select></div></div>');
    });
    html.push('</div>');

    if (isApproval) {
      html.push('<div class="prop-group"><h4>قاعده تأیید</h4>');
      html.push(row('چند نفر باید تأیید کنند؟',
        '<select id="p-approval-mode">' +
        options(S.data.approval_modes, cfg.approval_mode || 'any') + '</select>'));
      html.push(row('حد نصاب (وقتی «حداقل تعدادی» انتخاب شده)',
        '<input id="p-quorum" type="number" min="1" value="' +
        (cfg.approval_quorum || 2) + '">'));
      html.push(check('p-reject-first', 'یک «رد» برای برگرداندن فرایند کافی است',
        cfg.reject_on_first));
      html.push(row('در صورت رد، به کدام گره برگردد؟',
        '<select id="p-on-reject"><option value="">گره قبلی (پیش‌فرض)</option>' +
        S.design.graph.nodes.filter(function (n) { return n.type === 'phase'; })
          .map(function (n) {
            return '<option value="' + esc(n.key) + '"' +
              (cfg.on_reject_node === n.key ? ' selected' : '') + '>' +
              esc(n.title) + '</option>';
          }).join('') + '</select>' +
        '<p class="hint">اگر پیکان «در صورت رد» کشیده باشید، همان مقدم است.</p>'));
      html.push('</div>');
    }

    if (isAction) {
      html.push('<div class="prop-group"><h4>اقدام خودکار</h4>');
      html.push(row('چه کاری انجام شود؟', '<select id="p-action">' +
        options(S.data.actions, cfg.action || 'none') + '</select>'));
      html.push('</div>');
    }

    if (isStart) {
      html.push('<div class="prop-group"><h4>اجازه شروع</h4>');
      html.push(row('دسترسی لازم برای شروع این فرایند',
        '<input id="p-start-perm" value="' + esc(cfg.start_permission || '') +
        '" placeholder="مثلاً workflow.start">' +
        '<p class="hint">خالی یعنی فقط متولی‌های همین گره (و مدیر سیستم).</p>'));
      html.push('</div>');
    }

    html.push('<div class="prop-group"><h4>رفتار</h4>');
    html.push(check('p-wait', 'تا تکمیل گره‌های پیش از خود منتظر بماند',
      cfg.wait_for_predecessors !== undefined
        ? cfg.wait_for_predecessors
        : ['approval', 'action', 'end'].indexOf(node.type) >= 0));
    html.push('<p class="hint">فازها به‌صورت پیش‌فرض منتظر نمی‌مانند؛ متولی هر ' +
      'فاز هر وقت بخواهد آن را پر می‌کند و فقط هشدار می‌گیرد که فاز قبلی هنوز ' +
      'ثبت نشده است.</p>');
    html.push(check('p-active', 'روی نقشه فعال است', node.is_active !== false));
    html.push('<div class="prop-two">' +
      row('X', '<input id="p-x" type="number" value="' + Math.round(node.x || 0) + '">') +
      row('Y', '<input id="p-y" type="number" value="' + Math.round(node.y || 0) + '">') +
      row('عرض', '<input id="p-w" type="number" value="' +
        Math.round(node.width || 200) + '">') +
      row('ارتفاع', '<input id="p-h" type="number" value="' +
        Math.round(node.height || 90) + '">') + '</div>');
    html.push('</div>');

    // the form this node asks for
    html.push('<div class="prop-group"><h4>فرم این گره</h4>' +
      '<ul class="wf-drop" id="p-items"></ul>' +
      '<p class="hint">بخش‌ها و فیلدها را از پالت سمت راست روی این کادر بکشید. ' +
      '«فقط خواندنی» یعنی مقدارش نشان داده می‌شود ولی اینجا تغییر نمی‌کند.</p>' +
      '</div>');

    html.push('<div class="prop-actions">' +
      '<button class="btn-primary" id="p-save" type="button">💾 ذخیره گره</button>' +
      '<button class="btn-ghost" id="p-connect-from" type="button">➶ پیکان از این گره</button>' +
      '<button class="btn-ghost danger" id="p-delete" type="button">🗑 حذف گره</button>' +
      '</div>');

    host.innerHTML = html.join('');
    renderItems(node);
    bindPeople(host, node);
    host.querySelector('#p-save').onclick = function () { saveNode(node); };
    host.querySelector('#p-delete').onclick = function () { deleteNode(node); };
    host.querySelector('#p-connect-from').onclick = function () {
      S.connectFrom = node; if (!S.connecting) toggleConnect(); else updateConnectHint();
    };
    host.querySelectorAll('input,select,textarea').forEach(function (input) {
      input.disabled = !mayEdit();
    });
  }

  function row(label, control) {
    return '<div class="prop-row"><label>' + esc(label) + '</label>' + control +
      '</div>';
  }
  function check(id, label, value) {
    return '<label class="wf-check"><input type="checkbox" id="' + id + '"' +
      (value ? ' checked' : '') + '> ' + esc(label) + '</label>';
  }

  function renderItems(node) {
    var list = document.getElementById('p-items');
    if (!list) return;
    var items = node.items || [];
    list.innerHTML = items.length ? '' :
      '<li class="wf-drop-empty">این گره فرمی ندارد.</li>';
    items.forEach(function (item, index) {
      var li = document.createElement('li');
      li.className = 'wf-drop-item';
      li.innerHTML = '<span class="grip">⋮⋮</span>' +
        '<span class="wf-item-name">' +
        (item.kind === 'section' ? '▦ ' : '◽ ') + esc(item.title || item.code) +
        '</span>' +
        '<label class="mini-check"><input type="checkbox" class="i-opt"' +
        (item.is_optional ? ' checked' : '') + '> اختیاری</label>' +
        '<label class="mini-check"><input type="checkbox" class="i-ro"' +
        (item.is_read_only ? ' checked' : '') + '> فقط خواندنی</label>' +
        '<button type="button" class="i-del">✕</button>';
      li.querySelector('.i-del').onclick = function () {
        items.splice(index, 1); renderItems(node); saveItems(node);
      };
      li.querySelector('.i-opt').onchange = function () {
        item.is_optional = this.checked; saveItems(node);
      };
      li.querySelector('.i-ro').onchange = function () {
        item.is_read_only = this.checked; saveItems(node);
      };
      list.appendChild(li);
    });
    list.ondragover = function (ev) { ev.preventDefault(); list.classList.add('over'); };
    list.ondragleave = function () { list.classList.remove('over'); };
    list.ondrop = function (ev) {
      ev.preventDefault();
      list.classList.remove('over');
      var payload;
      try { payload = JSON.parse(ev.dataTransfer.getData('text/plain')); }
      catch (e) { return; }
      if (!payload || !payload.kind) return;
      node.items = (node.items || []).concat([{
        kind: payload.kind,
        section_id: payload.kind === 'section' ? payload.id : null,
        field_id: payload.kind === 'field' ? payload.id : null,
        title: payload.title, is_optional: false, is_read_only: false
      }]);
      renderItems(node);
      saveItems(node);
    };
  }

  async function saveItems(node) {
    try {
      var res = await App.api.put('/api/workflow/nodes/' + node.id + '/items', {
        items: (node.items || []).map(function (item) {
          return {
            kind: item.kind,
            id: item.kind === 'section' ? item.section_id : item.field_id,
            is_optional: !!item.is_optional, is_read_only: !!item.is_read_only
          };
        })
      });
      node.items = res.data.items;
      App.toast('فرم گره ذخیره شد.', 'success');
    } catch (err) { App.toast(err.message, 'error'); }
  }

  function bindPeople(host, node) {
    host.querySelectorAll('.p-add').forEach(function (select) {
      select.onchange = function () {
        if (!this.value) return;
        var parts = this.value.split(':');
        node.principals = (node.principals || []).concat([{
          role: this.dataset.role,
          principal_kind: parts[0],
          user_id: parts[0] === 'user' ? Number(parts[1]) : null,
          role_code: parts[0] === 'role' ? parts[1] : null,
          name: this.options[this.selectedIndex].textContent
        }]);
        this.value = '';
        renderProps();
      };
    });
    host.querySelectorAll('.p-remove').forEach(function (btn) {
      btn.onclick = function () {
        var chip = btn.parentNode;
        var role = chip.parentNode.dataset.role;
        node.principals = (node.principals || []).filter(function (p) {
          if (p.role !== role) return true;
          var sameUser = String(p.user_id || '') === chip.dataset.user;
          var sameCode = String(p.role_code || '') === chip.dataset.code;
          return !(sameUser && sameCode);
        });
        renderProps();
      };
    });
  }

  async function saveNode(node) {
    var cfg = Object.assign({}, node.config || {});
    var pick = function (id) { return document.getElementById(id); };
    if (pick('p-approval-mode')) {
      cfg.approval_mode = pick('p-approval-mode').value;
      cfg.approval_quorum = Number(pick('p-quorum').value) || 2;
      cfg.reject_on_first = pick('p-reject-first').checked;
      cfg.on_reject_node = pick('p-on-reject').value || null;
    }
    if (pick('p-action')) cfg.action = pick('p-action').value;
    if (pick('p-start-perm')) {
      cfg.start_permission = pick('p-start-perm').value.trim() || null;
    }
    cfg.wait_for_predecessors = pick('p-wait').checked;
    try {
      var res = await App.api.put('/api/workflow/nodes/' + node.id, {
        title: pick('p-title').value,
        node_type: pick('p-type').value,
        icon: pick('p-icon').value,
        description: pick('p-desc').value,
        stage_number: pick('p-number').value,
        x: pick('p-x').value, y: pick('p-y').value,
        width: pick('p-w').value, height: pick('p-h').value,
        is_active: pick('p-active').checked,
        config: cfg,
        principals: (node.principals || []).map(function (p) {
          return { role: p.role, kind: p.principal_kind || 'user',
            user_id: p.user_id, role_code: p.role_code };
        })
      });
      Object.assign(node, {
        title: res.data.title, type: res.data.node_type, icon: res.data.icon,
        description: res.data.description, stage_number: res.data.stage_number,
        x: res.data.x, y: res.data.y, width: res.data.width,
        height: res.data.height, config: res.data.config,
        is_active: res.data.is_active, principals: res.data.principals
      });
      App.toast('گره ذخیره شد.', 'success');
      draw(S.design); renderProps();
    } catch (err) { App.toast(err.message, 'error'); }
  }

  async function addNode(type) {
    var canvas = document.getElementById('wf-canvas').getBoundingClientRect();
    try {
      var res = await App.api.post('/api/workflow/nodes', {
        workflow_id: S.workflowId, node_type: type,
        title: 'گره جدید',
        x: Math.round((canvas.width / 2 - S.panX) / S.zoom),
        y: Math.round((canvas.height / 2 - S.panY) / S.zoom)
      });
      await load(S.workflowId);
      select('node', res.data.id);
    } catch (err) { App.toast(err.message, 'error'); }
  }

  async function deleteNode(node) {
    var confirmed = await App.confirmDialog({
      title: 'حذف گره',
      message: 'گره «' + node.title + '» از نقشه برداشته شود؟ اگر فرایندی از ' +
        'آن عبور کرده باشد، سابقه‌اش حفظ می‌شود.'
    });
    if (!confirmed) return;
    try {
      var res = await App.api.del('/api/workflow/nodes/' + node.id);
      App.toast(res.message || 'گره حذف شد.', 'success');
      S.selection = null;
      await load(S.workflowId);
    } catch (err) { App.toast(err.message, 'error'); }
  }

  function removeSelected() {
    if (!S.selection || !mayEdit()) return;
    if (S.selection.kind === 'node') deleteNode(nodeById(S.design, S.selection.id));
    else deleteEdge(edgeById(S.design, S.selection.id));
  }

  /* ── arrows ───────────────────────────────────────────────────────── */
  function toggleConnect() {
    S.connecting = !S.connecting;
    if (!S.connecting) S.connectFrom = null;
    document.getElementById('wf-canvas')
      .classList.toggle('connecting', S.connecting);
    document.getElementById('wf-connect')
      .classList.toggle('btn-primary', S.connecting);
    updateConnectHint();
  }

  function updateConnectHint() {
    var hint = document.getElementById('wf-connect-hint');
    if (!S.connecting) {
      hint.textContent = 'ابتدا این دکمه، سپس گره مبدأ و بعد گره مقصد.';
    } else if (!S.connectFrom) {
      hint.textContent = 'گره مبدأ را انتخاب کنید (Esc برای انصراف).';
    } else {
      hint.textContent = 'مبدأ: «' + S.connectFrom.title + '» — حالا گره مقصد.';
    }
  }

  async function pickForConnect(node) {
    if (!S.connectFrom) { S.connectFrom = node; updateConnectHint(); return; }
    if (S.connectFrom.id === node.id) { App.toast('مبدأ و مقصد یکی است.', 'error'); return; }
    try {
      var res = await App.api.post('/api/workflow/edges', {
        source_id: S.connectFrom.id, target_id: node.id
      });
      S.connectFrom = null;
      toggleConnect();
      await load(S.workflowId);
      select('edge', res.data.id);
    } catch (err) { App.toast(err.message, 'error'); }
  }

  function edgeProps(host, edge) {
    var from = nodeByKey(S.design, edge.source_key || edge.source);
    var to = nodeByKey(S.design, edge.target_key || edge.target);
    var html = ['<div class="prop-group">'];
    html.push('<p class="hint">از «' + esc(from ? from.title : '?') + '» به «' +
      esc(to ? to.title : '?') + '»</p>');
    html.push(row('برچسب روی پیکان',
      '<input id="e-label" value="' + esc(edge.label || '') + '">'));
    html.push(row('نوع پیکان', '<select id="e-kind">' +
      options(S.data.edge_kinds, edge.kind || 'default') + '</select>'));
    html.push(row('مقصد', '<select id="e-target">' +
      S.design.graph.nodes.map(function (n) {
        return '<option value="' + n.id + '"' +
          (to && n.id === to.id ? ' selected' : '') + '>' + esc(n.title) +
          '</option>';
      }).join('') + '</select>'));
    html.push(row('اولویت (کمتر، زودتر بررسی می‌شود)',
      '<input id="e-priority" type="number" value="' + (edge.priority || 0) + '">'));
    html.push(row('توضیح',
      '<textarea id="e-desc" rows="2">' + esc(edge.description || '') +
      '</textarea>'));
    html.push('</div>');

    html.push('<div class="prop-group"><h4>شرط عبور</h4>');
    html.push(row('همه شرط‌ها / یکی از شرط‌ها',
      '<select id="e-join"><option value="all">همه برقرار باشند</option>' +
      '<option value="any"' + (joinOf(edge) === 'any' ? ' selected' : '') +
      '>یکی کافی است</option></select>'));
    html.push('<div id="e-conds"></div>');
    html.push('<button class="btn-ghost" id="e-add-cond" type="button">➕ شرط</button>');
    html.push('<p class="hint">بدون شرط یعنی پیکان همیشه طی می‌شود. شرطی که ' +
      'به پاسخی اشاره کند که هنوز داده نشده، برقرار نیست — و همین است که یک ' +
      'شاخه را تا رسیدن پاسخ بسته نگه می‌دارد.</p>');
    html.push('</div>');

    html.push('<div class="prop-actions">' +
      '<button class="btn-primary" id="e-save" type="button">💾 ذخیره پیکان</button>' +
      '<button class="btn-ghost danger" id="e-delete" type="button">🗑 حذف پیکان</button>' +
      '</div>');
    host.innerHTML = html.join('');
    renderConditions(edge);
    host.querySelector('#e-add-cond').onclick = function () {
      edge._rows = conditionRows(edge).concat([{ field: '', op: 'eq', value: '' }]);
      renderConditions(edge);
    };
    host.querySelector('#e-save').onclick = function () { saveEdge(edge); };
    host.querySelector('#e-delete').onclick = function () { deleteEdge(edge); };
    host.querySelectorAll('input,select,textarea').forEach(function (input) {
      input.disabled = !mayEdit();
    });
  }

  function joinOf(edge) {
    var c = edge.condition || {};
    return c.any ? 'any' : 'all';
  }

  function conditionRows(edge) {
    if (edge._rows) return edge._rows;
    var c = edge.condition || {};
    var list = c.all || c.any || (c.field ? [c] : []);
    edge._rows = list.filter(function (r) { return r && r.field; })
      .map(function (r) {
        return { field: r.field, op: r.op || 'eq',
          value: Array.isArray(r.value) ? r.value.join('، ') : (r.value || '') };
      });
    return edge._rows;
  }

  function renderConditions(edge) {
    var host = document.getElementById('e-conds');
    if (!host) return;
    var rows = conditionRows(edge);
    host.innerHTML = rows.length ? '' : '<p class="hint">بدون شرط.</p>';
    rows.forEach(function (rowData, index) {
      var div = document.createElement('div');
      div.className = 'cond-row';
      div.innerHTML =
        '<select class="c-field"><option value="">— فیلد —</option>' +
        S.data.field_names.map(function (f) {
          return '<option value="' + esc(f.value) + '"' +
            (f.value === rowData.field ? ' selected' : '') + '>' +
            esc(f.label) + '</option>';
        }).join('') + '</select>' +
        '<select class="c-op">' + options(S.data.operators, rowData.op) + '</select>' +
        '<input class="c-value" value="' + esc(rowData.value) + '">' +
        '<button type="button" class="c-del">✕</button>';
      div.querySelector('.c-field').onchange = function () { rowData.field = this.value; };
      div.querySelector('.c-op').onchange = function () { rowData.op = this.value; };
      div.querySelector('.c-value').oninput = function () { rowData.value = this.value; };
      div.querySelector('.c-del').onclick = function () {
        rows.splice(index, 1); renderConditions(edge);
      };
      host.appendChild(div);
    });
  }

  function buildCondition(edge) {
    var rows = conditionRows(edge).filter(function (r) { return r.field; });
    if (!rows.length) return null;
    var parts = rows.map(function (r) {
      var value = String(r.value || '');
      var many = value.indexOf('،') >= 0;
      return {
        field: r.field, op: r.op,
        value: many ? value.split('،').map(function (v) { return v.trim(); })
          : value
      };
    });
    if (parts.length === 1) return parts[0];
    var join = document.getElementById('e-join').value;
    var out = {};
    out[join] = parts;
    return out;
  }

  async function saveEdge(edge) {
    try {
      var res = await App.api.put('/api/workflow/edges/' + edge.id, {
        label: document.getElementById('e-label').value,
        kind: document.getElementById('e-kind').value,
        target_id: Number(document.getElementById('e-target').value),
        priority: document.getElementById('e-priority').value,
        description: document.getElementById('e-desc').value,
        condition: buildCondition(edge)
      });
      delete edge._rows;
      App.toast('پیکان ذخیره شد.', 'success');
      await load(S.workflowId);
      select('edge', res.data.id);
    } catch (err) { App.toast(err.message, 'error'); }
  }

  async function deleteEdge(edge) {
    var confirmed = await App.confirmDialog({
      title: 'حذف پیکان', message: 'این اتصال حذف شود؟'
    });
    if (!confirmed) return;
    try {
      await App.api.del('/api/workflow/edges/' + edge.id);
      S.selection = null;
      await load(S.workflowId);
    } catch (err) { App.toast(err.message, 'error'); }
  }

  /* ── template actions ─────────────────────────────────────────────── */
  async function saveTemplate() {
    try {
      await App.api.put('/api/workflow/templates/' + S.workflowId, {
        status: document.getElementById('wf-status').value,
        is_active: document.getElementById('wf-active').checked
      });
      App.toast('مشخصات فرایند ذخیره شد.', 'success');
      await load(S.workflowId);
    } catch (err) { App.toast(err.message, 'error'); }
  }

  async function newVersion() {
    var confirmed = await App.confirmDialog({
      title: 'نسخه جدید', danger: false, confirmText: 'بساز',
      message: 'یک کپی از این نقشه به‌عنوان نسخه بعدی ساخته می‌شود. ' +
        'فرایندهای در جریان روی نسخه‌ی خودشان می‌مانند.'
    });
    if (!confirmed) return;
    try {
      var res = await App.api.post(
        '/api/workflow/templates/' + S.workflowId + '/version', {});
      App.toast(res.message, 'success');
      await load(res.data.id);
    } catch (err) { App.toast(err.message, 'error'); }
  }

  async function newTemplate() {
    var name = window.prompt('نام فرایند جدید:');
    if (!name) return;
    var code = window.prompt('شناسه انگلیسی (اختیاری، برای ارجاع فنی):', '');
    try {
      var res = await App.api.post('/api/workflow/templates',
        { name: name, code: code || '' });
      App.toast('فرایند ساخته شد. حالا گره‌ها و پیکان‌ها را بکشید.', 'success');
      await load(res.data.id);
    } catch (err) { App.toast(err.message, 'error'); }
  }

  async function deleteTemplate() {
    var confirmed = await App.confirmDialog({
      title: 'حذف فرایند',
      message: 'کل این فرایند حذف شود؟ اگر اجرایی داشته باشد، به‌جای حذف ' +
        'بایگانی می‌شود.'
    });
    if (!confirmed) return;
    try {
      var res = await App.api.del('/api/workflow/templates/' + S.workflowId);
      App.toast(res.message || 'انجام شد.', 'success');
      await load();
    } catch (err) { App.toast(err.message, 'error'); }
  }

  /* ── monitor ──────────────────────────────────────────────────────── */
  async function loadInstances() {
    var host = document.getElementById('mon-list');
    host.innerHTML = '<div class="loading">در حال بارگذاری</div>';
    var status = document.getElementById('mon-status');
    var wfSelect = document.getElementById('mon-workflow');
    try {
      var query = [];
      if (status.value) query.push('status=' + encodeURIComponent(status.value));
      if (wfSelect.value) query.push('workflow_id=' + wfSelect.value);
      var res = await App.api.get('/api/workflow/instances' +
        (query.length ? '?' + query.join('&') : ''));
      if (!status.options.length && res.statuses) {
        status.innerHTML = '<option value="">همه وضعیت‌ها</option>' +
          options(res.statuses, '');
      }
      if (!wfSelect.options.length && S.data) {
        wfSelect.innerHTML = '<option value="">همه فرایندها</option>' +
          S.data.templates.map(function (t) {
            return '<option value="' + t.id + '">' + esc(t.name) + ' v' +
              t.version + '</option>';
          }).join('');
      }
      S.monitor.rows = res.data || [];
      renderInstances();
    } catch (err) {
      host.innerHTML = '<div class="alert error">' + esc(err.message) + '</div>';
    }
  }

  function renderInstances() {
    var host = document.getElementById('mon-list');
    if (!S.monitor.rows.length) {
      host.innerHTML = '<p class="empty">فرایندی با این شرایط نیست.</p>';
      return;
    }
    host.innerHTML = '<table class="table"><thead><tr><th>#</th><th>فرایند</th>' +
      '<th>موضوع</th><th>وضعیت</th><th>اکنون در</th><th>تاریخ</th></tr></thead>' +
      '<tbody>' + S.monitor.rows.map(function (r) {
        return '<tr class="wf-mon-row' +
          (S.monitor.selected === r.id ? ' selected' : '') +
          '" data-id="' + r.id + '"><td>' + r.id + '</td><td>' +
          esc(r.workflow_name || '') + '</td><td>' +
          esc(r.well || r.operation_label || '—') + '</td><td>' +
          esc(r.status_label) + '</td><td>' +
          esc(r.current_node_title || r.current_node || '—') + '</td><td>' +
          esc(r.created_at_j || '') + '</td></tr>';
      }).join('') + '</tbody></table>';
    host.querySelectorAll('.wf-mon-row').forEach(function (tr) {
      tr.onclick = function () { openInstance(Number(tr.dataset.id)); };
    });
  }

  async function openInstance(id) {
    S.monitor.selected = id;
    renderInstances();
    var detail = document.getElementById('mon-detail');
    detail.innerHTML = '<div class="loading">در حال بارگذاری</div>';
    try {
      var res = await App.api.get('/api/workflow/instances/' + id + '/map');
      // Painted on the run's *own* snapshot, not on today's drawing: a phase
      // the admin has since deleted is still where it was when this ran.
      S.mon.graph = res.data.graph;
      S.mon.live = res.data.map;
      var instance = res.data.instance;
      document.getElementById('mon-detail-title').textContent =
        'فرایند #' + id + ' — ' + (instance.workflow_name || '') +
        ' (نسخه ' + (instance.template_version || 1) + ')';
      detail.innerHTML =
        '<p class="hint">وضعیت: <b>' + esc(instance.status_label) + '</b>' +
        (instance.well ? ' · موضوع: ' + esc(instance.well) : '') + '</p>' +
        '<div class="wf-canvas-wrap" style="border:1px solid var(--border);' +
        'border-radius:10px;margin-top:8px">' +
        '<div class="wf-canvas" id="mon-canvas" style="height:360px">' +
        '<div class="wf-plane" id="mon-plane">' +
        '<svg class="wf-edges" id="mon-edges"></svg>' +
        '<div class="wf-nodes" id="mon-nodes"></div></div></div></div>' +
        timelineHtml(res.data.events);
      draw(S.mon);
      bindPan(S.mon);
      fitToScreen(S.mon);
    } catch (err) {
      detail.innerHTML = '<div class="alert error">' + esc(err.message) + '</div>';
    }
  }

  function timelineHtml(events) {
    if (!events || !events.length) return '';
    return '<h4 style="margin:14px 0 4px">سابقه</h4><ul class="wf-timeline">' +
      events.map(function (e) {
        return '<li><span class="t-when">' + esc(e.at_j || '') + ' ' +
          esc(e.at_time || '') + '</span><span><b>' + esc(e.action_label) +
          '</b>' + (e.user_name ? ' — ' + esc(e.user_name) : '') +
          (e.from_title || e.to_title
            ? ' <small>(' + esc(e.from_title || '') +
              (e.to_title ? ' ← ' + esc(e.to_title) : '') + ')</small>' : '') +
          (e.comment ? '<br><small>' + esc(e.comment) + '</small>' : '') +
          '</span></li>';
      }).join('') + '</ul>';
  }
})();
