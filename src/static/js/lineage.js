/* ============================================================
   祖师法脉 — 完整四面板仪表盘（嵌入首页版）
   迁移自 30_Lineage/static/app.js
   API 前缀: /api/lineage/
   ============================================================ */

// --- 宗派配色 ---
const SECT_COLORS = {
    '臨濟宗': '#c0392b', '臨濟': '#c0392b',
    '曹洞宗': '#27ae60', '曹洞': '#27ae60',
    '雲門宗': '#2980b9', '雲門': '#2980b9',
    '法眼宗': '#f39c12', '法眼': '#f39c12',
    '溈仰宗': '#8e44ad', '溈仰': '#8e44ad',
    '南宗': '#e67e22', '北宗': '#3498db',
    '石頭宗': '#1abc9c', '洪州宗': '#c0392b',
    '牛頭宗': '#16a085', '荷澤宗': '#d4a843',
    '楊岐派': '#e74c3c', '黃龍派': '#f1c40f',
    '天台宗': '#9b59b6', '華嚴宗': '#2ecc71',
    '淨土宗': '#3498db', '律宗': '#e67e22',
    '唯識宗': '#1abc9c', '密宗': '#e74c3c',
    '三論宗': '#95a5a6',
};
function getSectColor(sect) {
    if (!sect) return '#8899aa';
    for (const [key, color] of Object.entries(SECT_COLORS)) {
        if (sect.includes(key)) return color;
    }
    return '#8899aa';
}

// --- 状态 ---
const lnState = {
    currentPerson: null,
    currentPersonData: null,
    currentSect: null,
    lineageDepth: 2,
    lineageFullscreen: false,
    mapFullscreen: false,
    timelineInitialized: false,
    mapInitialized: false,
};

// --- 通用 fetch ---
async function lnFetchJSON(url) {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
}

function lnSetStatus(msg) {
    const el = document.getElementById('ln-status-msg');
    if (el) el.textContent = msg;
}

// ============================================================
// 搜索
// ============================================================
const lnSearchInput = document.getElementById('lineage-search-input');
const lnSearchResults = document.getElementById('lineage-search-results');

if (lnSearchInput) {
    let searchTimer = null;
    lnSearchInput.addEventListener('input', () => {
        clearTimeout(searchTimer);
        const q = lnSearchInput.value.trim();
        if (q.length < 1) { lnSearchResults.classList.remove('active'); return; }
        searchTimer = setTimeout(async () => {
            try {
                const data = await lnFetchJSON(`/api/lineage/search?q=${encodeURIComponent(q)}`);
                if (data.length === 0) {
                    lnSearchResults.innerHTML = '<div class="search-item" style="color:var(--text-muted)">未找到</div>';
                } else {
                    lnSearchResults.innerHTML = data.slice(0, 12).map(p => `
                        <div class="search-item" onclick="lnSelectPerson('${p.person_id}')">
                            <div class="name">${p.name}</div>
                            <div class="meta">${p.dynasty || ''} ${p.sect || ''} ${formatPersonYears(p.birth_year, p.death_year)}</div>
                        </div>
                    `).join('');
                }
                lnSearchResults.classList.add('active');
            } catch (e) { /* 忽略 */ }
        }, 250);
    });
}

// 点击外部关闭搜索
document.addEventListener('click', (e) => {
    if (!e.target.closest('.lineage-search-box')) {
        if (lnSearchResults) lnSearchResults.classList.remove('active');
    }
});

// 推荐词 Chips
const chipsEl = document.getElementById('lineage-search-chips');
if (chipsEl) {
    chipsEl.addEventListener('click', (e) => {
        const chip = e.target.closest('.chip');
        if (!chip) return;
        if (chip.dataset.founder) {
            lnSelectPerson(chip.dataset.founder);
        } else if (chip.dataset.q) {
            lnSearchInput.value = chip.dataset.q;
            lnSearchInput.dispatchEvent(new Event('input'));
        }
    });
}

// ============================================================
// 人物选择（核心联动）
// ============================================================
async function lnSelectPerson(personId) {
    if (lnSearchResults) lnSearchResults.classList.remove('active');
    if (lnSearchInput) lnSearchInput.value = '';
    lnState.currentPerson = personId;
    lnState.lineageDepth = 2;
    lnSetStatus('載入人物...');

    try {
        const person = await lnFetchJSON(`/api/lineage/person/${personId}`);
        lnState.currentPersonData = person;
        renderSidebar(person);

        // 法脉图 ego-centric 重绘
        renderEgoGraph(personId);

        // 编年高亮 + 地图飞入
        highlightTimeline(personId);
        highlightMap(personId);

        lnSetStatus(`${person.name} (${person.dynasty || '?'})`);
    } catch (e) {
        lnSetStatus('載入失敗: ' + e.message);
    }
}
// 全局别名
window.selectPerson = lnSelectPerson;
window.lnSelectPerson = lnSelectPerson;

// ============================================================
// 侧边栏渲染（三栏：生平 / 师承 / 著作）
// ============================================================
function renderSidebar(person) {
    document.getElementById('detail-title').innerHTML = `<i data-lucide="circle-user-round" class="ln-panel-icon"></i> 人物`;

    const yearStr = formatPersonYears(person.birth_year, person.death_year);
    const teacherCount = person.teachers ? person.teachers.length : 0;
    const studentCount = person.students ? person.students.length : 0;
    const socialCount = person.social ? person.social.length : 0;
    const worksLines = person.works ? person.works.trim().split('\n').filter(l => l.trim()) : [];
    const scriptureCount = person.scriptures ? person.scriptures.length : 0;
    const refsCount = (person.cbeta_refs && Array.isArray(person.cbeta_refs)) ? person.cbeta_refs.length : 0;

    let html = `<div class="sidebar-columns">`;

    // ===== 栏 1: 生平 =====
    html += `<div class="sidebar-col">
        <div class="sidebar-col-header"><i data-lucide="square-user" class="sidebar-icon"></i> 生平</div>
        <div class="sidebar-col-body">`;

    html += `<div class="person-meta">
        <div class="person-name">${person.name}</div>
        ${person.dynasty ? `<span class="tag dynasty">${person.dynasty}</span>` : ''}
        ${person.sect ? `<span class="tag sect" style="cursor:pointer" onclick="lnSearchInput.value='${person.sect}'; lnSearchInput.dispatchEvent(new Event('input'))">${person.sect}</span>` : ''}
        ${yearStr ? `<span class="tag">${yearStr}</span>` : ''}
        ${person.is_monk !== null && person.is_monk !== undefined ? `<span class="tag">${person.is_monk ? '僧' : '俗'}</span>` : ''}
        ${person.gender === 2 ? '<span class="tag">女</span>' : ''}
        ${person.aliases && person.aliases.length ? `<div style="margin-top:4px;font-size:11px;color:#6c7a8a">別名：${Array.isArray(person.aliases) ? person.aliases.join('、') : person.aliases}</div>` : ''}
    </div>`;

    if (person.bio_concise) {
        html += `<div class="person-section"><div class="person-bio">${person.bio_concise}</div></div>`;
    }
    if (person.bio_extensive) {
        html += `<div class="person-section">
            <h3 style="cursor:pointer" onclick="this.nextElementSibling.style.display = this.nextElementSibling.style.display === 'none' ? 'block' : 'none'"><i data-lucide="book-open-text" class="sidebar-icon"></i> 詳傳 ▸</h3>
            <div class="person-bio" style="display:none;font-size:12px;line-height:1.8;color:#9aa5b4">${person.bio_extensive}</div>
        </div>`;
    }
    if (person.place_origin) {
        html += `<div class="person-section">
            <h3><i data-lucide="map-pin" class="sidebar-icon"></i> 籍貫</h3>
            <div style="font-size:13px;color:#5ec4d4;cursor:pointer;text-decoration:underline dotted" onclick="highlightMap('${person.person_id}')">${person.place_origin.split('\n')[0]}</div>
        </div>`;
    }
    if (!person.bio_concise && !person.bio_extensive && !person.place_origin) {
        html += `<div class="ln-empty-state">暫無生平資料</div>`;
    }
    html += `</div></div>`;

    // ===== 栏 2: 师承 =====
    html += `<div class="sidebar-col">
        <div class="sidebar-col-header"><i data-lucide="list-tree" class="sidebar-icon"></i> 師承</div>
        <div class="sidebar-col-body">`;

    if (person.teachers && person.teachers.length) {
        html += `<div class="person-section"><h3>師父 (${person.teachers.length})</h3>
            <div class="tag-flow">
                ${person.teachers.map(t => `<span class="tag-person" onclick="lnSelectPerson('${t.person_id}')">${t.name}</span>`).join('、')}
            </div></div>`;
    }
    if (person.students && person.students.length) {
        html += `<div class="person-section"><h3>弟子 (${person.students.length})</h3>
            <div class="tag-flow">
                ${person.students.map(s => `<span class="tag-person" onclick="lnSelectPerson('${s.person_id}')">${s.name}</span>`).join('、')}
            </div></div>`;
    }
    if (person.social && person.social.length > 0) {
        html += `<div class="person-section"><h3>法友 (${person.social.length})</h3>
            <div class="tag-flow">
                ${person.social.map(s => `<span class="tag-person" onclick="lnSelectPerson('${s.person_id}')">${s.name}</span>`).join('、')}
            </div></div>`;
    }
    if (!teacherCount && !studentCount && !socialCount) {
        html += `<div class="ln-empty-state">暫無師承</div>`;
    }
    html += `</div></div>`;

    // ===== 栏 3: 著作 =====
    html += `<div class="sidebar-col">
        <div class="sidebar-col-header"><i data-lucide="book-open-text" class="sidebar-icon"></i> 著作</div>
        <div class="sidebar-col-body">`;

    if (worksLines.length > 0) {
        const items = worksLines.map(w => {
            const m = w.match(/(.+?)\((\w+)\)/);
            if (m) {
                return `<li><a href="https://cbetaonline.dila.edu.tw/${m[2]}" target="_blank" style="color:#5ec4d4;text-decoration:none">${m[1].trim()}</a> <span class="label">${m[2]}</span></li>`;
            }
            return `<li>${w}</li>`;
        }).join('');
        html += `<div class="person-section"><h3>著作 (${worksLines.length})</h3>
            <ul class="scripture-list">${items}</ul></div>`;
    }
    if (person.scriptures && person.scriptures.length) {
        html += `<div class="person-section"><h3>相關經典 (${person.scriptures.length})</h3>
            <ul class="scripture-list">
                ${person.scriptures.map(s => `
                    <li>
                        <span class="type ${s.relation}">${s.relation === 'authored' ? '著' : s.relation === 'mentioned' ? '提' : '引'}</span>
                        <a href="${s.url || 'https://cbetaonline.dila.edu.tw/' + s.scripture_id}" target="_blank" style="color:#5ec4d4;text-decoration:none">
                            <span class="sid">${s.scripture_id}</span>
                        </a>
                        ${s.source_text ? `<span>${s.source_text.substring(0, 30)}</span>` : ''}
                    </li>
                `).join('')}
            </ul></div>`;
    }
    if (person.cbeta_refs && Array.isArray(person.cbeta_refs) && person.cbeta_refs.length > 0) {
        const items = person.cbeta_refs.map(ref => {
            const m = ref.match(/CBETA\s+(\w+)/);
            if (m) {
                const sid = m[1].replace(/_.*/, '');
                const title = ref.replace(/\(.*?\)\s*/, '').trim();
                return `<li><a href="https://cbetaonline.dila.edu.tw/${sid}" target="_blank" style="color:#5ec4d4;text-decoration:none;font-size:12px">${title}</a></li>`;
            }
            return `<li style="font-size:12px">${ref}</li>`;
        }).join('');
        html += `<div class="person-section"><h3>文獻引用 (${person.cbeta_refs.length})</h3>
            <ul class="scripture-list">${items}</ul></div>`;
    }
    if (!worksLines.length && !scriptureCount && !refsCount) {
        html += `<div class="ln-empty-state">暫無著作</div>`;
    }
    html += `</div></div>`;

    html += `</div>`; // sidebar-columns

    document.getElementById('detail-content').innerHTML = html;
    if (typeof lucide !== 'undefined') lucide.createIcons();
}

// ============================================================
// 🌳 Ego-centric 法脉图
// ============================================================
const lnTooltip = document.getElementById('ln-tooltip');

async function renderEgoGraph(personId) {
    const container = document.getElementById('lineage-container');
    const empty = document.getElementById('lineage-empty');
    if (!personId) { if (empty) empty.style.display = ''; return; }

    try {
        const depth = lnState.lineageDepth || 2;
        const data = await lnFetchJSON(`/api/lineage/lineage/${personId}?depth=${depth}`);

        // 更新追溯按钮状态
        const expandBtn = document.getElementById('lineage-expand-btn');
        if (expandBtn) {
            expandBtn.disabled = !personId;
            if (depth >= 4) {
                expandBtn.innerHTML = '<i data-lucide="search" style="width:12px;height:12px;vertical-align:middle"></i> 上限';
                expandBtn.disabled = true;
            } else {
                expandBtn.innerHTML = depth > 2
                    ? `<i data-lucide="search" style="width:12px;height:12px;vertical-align:middle"></i> 深度 ${depth}`
                    : '<i data-lucide="search" style="width:12px;height:12px;vertical-align:middle"></i> 追溯';
            }
            if (typeof lucide !== 'undefined') lucide.createIcons();
        }
        if (empty) empty.style.display = 'none';
        container.querySelectorAll('svg').forEach(s => s.remove());

        const width = container.clientWidth || 400;
        const height = container.clientHeight || 300;
        const svg = d3.select(container).append('svg')
            .attr('width', width).attr('height', height);
        const g = svg.append('g');

        if (!data.nodes || data.nodes.length === 0) {
            if (empty) { empty.style.display = ''; }
            return;
        }

        // 节点数量保护
        if (data.nodes.length > 500) {
            lnSetStatus(`ℹ️ 節點過多 (${data.nodes.length})，僅顯示前 500 個`);
            data.nodes = data.nodes.slice(0, 500);
            const nodeIds = new Set(data.nodes.map(n => n.person_id));
            data.edges = (data.edges || []).filter(e => nodeIds.has(e.source) && nodeIds.has(e.target));
        }

        // 构建邻接表
        data.nodes.forEach(n => { n.id = n.person_id; });
        const nodeMap = new Map(data.nodes.map(n => [n.id, { ...n }]));
        const childrenMap = new Map();
        const parentsMap = new Map();
        (data.edges || []).forEach(e => {
            if (!childrenMap.has(e.source)) childrenMap.set(e.source, []);
            childrenMap.get(e.source).push(e.target);
            if (!parentsMap.has(e.target)) parentsMap.set(e.target, []);
            parentsMap.get(e.target).push(e.source);
        });

        // BFS 分层
        const layers = new Map();
        const visited = new Set();
        const queue = [{ id: personId, layer: 0 }];
        visited.add(personId);

        while (queue.length > 0) {
            const { id, layer } = queue.shift();
            if (!layers.has(layer)) layers.set(layer, []);
            layers.get(layer).push(id);
            if (layer > -2) {
                (parentsMap.get(id) || []).forEach(tid => {
                    if (!visited.has(tid) && nodeMap.has(tid)) {
                        visited.add(tid); queue.push({ id: tid, layer: layer - 1 });
                    }
                });
            }
            if (layer < 2) {
                (childrenMap.get(id) || []).forEach(sid => {
                    if (!visited.has(sid) && nodeMap.has(sid)) {
                        visited.add(sid); queue.push({ id: sid, layer: layer + 1 });
                    }
                });
            }
        }

        // 水平树形布局
        const layerNums = [...layers.keys()].sort((a, b) => a - b);
        const totalLayers = layerNums.length;
        const colSpacing = Math.max(100, width / (totalLayers + 1));

        const simNodes = [];
        const layerIndex = new Map();

        layerNums.forEach((ln, colIdx) => {
            const ids = layers.get(ln);
            const count = ids.length;
            const targetX = (colIdx + 1) * colSpacing;

            ids.forEach((id, j) => {
                const nd = nodeMap.get(id);
                if (!nd) return;
                const isEgo = id === personId;

                let targetY;
                if (isEgo) {
                    targetY = height / 2;
                } else if (count === 1) {
                    targetY = height / 2;
                } else {
                    const usableHeight = Math.min(height * 0.85, count * 28);
                    const startY = height / 2 - usableHeight / 2;
                    targetY = startY + (j / (count - 1)) * usableHeight;
                }

                simNodes.push({
                    ...nd,
                    layer: ln,
                    targetX, targetY,
                    x: targetX + (Math.random() - 0.5) * 10,
                    y: targetY + (Math.random() - 0.5) * 10,
                    fx: isEgo ? targetX : null,
                    fy: isEgo ? height / 2 : null,
                });
                layerIndex.set(id, ln);
            });
        });

        const simNodeMap = new Map(simNodes.map(n => [n.id, n]));

        const simLinks = (data.edges || [])
            .filter(e => simNodeMap.has(e.source) && simNodeMap.has(e.target))
            .map(e => ({
                source: simNodeMap.get(e.source),
                target: simNodeMap.get(e.target),
                description: e.description,
                cbeta_ref: e.cbeta_ref,
            }));

        // 力仿真
        const simulation = d3.forceSimulation(simNodes)
            .force('x', d3.forceX(d => d.targetX).strength(0.6))
            .force('y', d3.forceY(d => d.targetY).strength(0.6))
            .force('collide', d3.forceCollide(20))
            .force('charge', d3.forceManyBody().strength(-30))
            .stop();

        for (let i = 0; i < 300; i++) simulation.tick();

        // 绘制边
        simLinks.forEach(e => {
            const sx = e.source.x, sy = e.source.y;
            const tx = e.target.x, ty = e.target.y;
            const mx = (sx + tx) / 2;
            const isEgoEdge = e.source.id === personId || e.target.id === personId;

            // hover 命中区
            g.append('path')
                .attr('d', `M${sx},${sy} C${mx},${sy} ${mx},${ty} ${tx},${ty}`)
                .attr('fill', 'none').attr('stroke', 'transparent').attr('stroke-width', 12)
                .attr('cursor', e.description ? 'help' : 'default')
                .on('mouseenter', (event) => {
                    if (!e.description) return;
                    const desc = e.description.length > 120 ? e.description.substring(0, 120) + '…' : e.description;
                    let tipHtml = `<div style="font-size:12px;line-height:1.6;max-width:320px">`;
                    tipHtml += `<div style="color:#e8c468;font-size:11px;margin-bottom:4px">📖 師承出處</div>`;
                    tipHtml += `<div style="color:#c0c8d4">${desc}</div>`;
                    if (e.cbeta_ref) {
                        tipHtml += `<div style="margin-top:4px"><a href="${e.cbeta_ref}" target="_blank" style="color:#5ec4d4;font-size:11px;text-decoration:none">🔗 CBETA 原文 →</a></div>`;
                    }
                    tipHtml += `</div>`;
                    lnTooltip.innerHTML = tipHtml;
                    lnTooltip.style.display = 'block';
                    lnTooltip.style.left = (event.pageX + 12) + 'px';
                    lnTooltip.style.top = (event.pageY - 10) + 'px';
                })
                .on('mouseleave', () => { lnTooltip.style.display = 'none'; });

            // 可见路径
            g.append('path')
                .attr('d', `M${sx},${sy} C${mx},${sy} ${mx},${ty} ${tx},${ty}`)
                .attr('fill', 'none')
                .attr('stroke', isEgoEdge ? '#d4a843' : (document.body.classList.contains('theme-light') ? '#c0b8a0' : '#3a4557'))
                .attr('stroke-width', isEgoEdge ? 2 : 1)
                .attr('stroke-opacity', 0.6)
                .attr('pointer-events', 'none');
        });

        // 绘制节点
        simNodes.forEach(n => {
            const isEgo = n.id === personId;
            const color = n.sect ? getSectColor(n.sect) : '#8899aa';
            const r = isEgo ? 10 : 6;

            const ng = g.append('g')
                .attr('transform', `translate(${n.x},${n.y})`)
                .attr('cursor', 'pointer')
                .on('click', () => { if (!isEgo) lnSelectPerson(n.id); });

            if (isEgo) {
                ng.append('circle').attr('r', r + 4)
                    .attr('fill', 'none').attr('stroke', '#d4a843')
                    .attr('stroke-width', 2).attr('stroke-opacity', 0.3);
            }

            ng.append('circle').attr('r', r)
                .attr('fill', color).attr('fill-opacity', 0.85)
                .attr('stroke', isEgo ? '#d4a843' : (document.body.classList.contains('theme-light') ? '#8a7a60' : '#fff'))
                .attr('stroke-width', isEgo ? 2 : 0.5)
                .attr('stroke-opacity', isEgo ? 0.8 : 0.3);

            const textAnchor = isEgo ? 'middle' : (n.layer < 0 ? 'end' : 'start');
            const textDx = isEgo ? 0 : (n.layer < 0 ? -(r + 4) : r + 4);
            const textDy = isEgo ? r + 14 : 4;

            ng.append('text')
                .attr('x', textDx).attr('y', textDy)
                .attr('text-anchor', textAnchor)
                .attr('fill', isEgo ? (document.body.classList.contains('theme-light') ? '#8b6914' : '#e8c468') : (document.body.classList.contains('theme-light') ? '#3c2e1a' : '#c0c8d4'))
                .attr('font-size', isEgo ? '12px' : '10px')
                .attr('font-weight', isEgo ? '700' : '400')
                .attr('font-family', '"Noto Serif CJK SC", serif')
                .text(n.name);

            // 工具提示
            ng.on('mouseenter', (event) => {
                const ys = formatPersonYears(n.birth_year, n.death_year);
                lnTooltip.innerHTML = `<div style="font-size:13px;font-weight:600">${n.name}</div>
                    ${n.dynasty ? `<div style="color:#9aa5b4;font-size:11px">${n.dynasty}</div>` : ''}
                    ${ys ? `<div style="color:#9aa5b4;font-size:11px">${ys}</div>` : ''}
                    ${n.sect ? `<div style="color:${color};font-size:11px">${n.sect}</div>` : ''}`;
                lnTooltip.style.display = 'block';
                lnTooltip.style.left = (event.pageX + 12) + 'px';
                lnTooltip.style.top = (event.pageY - 10) + 'px';
            })
                .on('mouseleave', () => { lnTooltip.style.display = 'none'; });
        });

        // 缩放
        const zoom = d3.zoom().scaleExtent([0.3, 4])
            .on('zoom', (event) => g.attr('transform', event.transform));
        svg.call(zoom);

        // 自动适配视图
        const allX = simNodes.map(n => n.x);
        const allY = simNodes.map(n => n.y);
        const pad = 60;
        const bx = Math.min(...allX) - pad, by = Math.min(...allY) - pad;
        const bw = Math.max(...allX) - bx + pad * 2;
        const bh = Math.max(...allY) - by + pad * 2;
        const scale = Math.min(width / bw, height / bh, 1.5);
        const ttx = (width - bw * scale) / 2 - bx * scale;
        const tty = (height - bh * scale) / 2 - by * scale;
        svg.transition().duration(400)
            .call(zoom.transform, d3.zoomIdentity.translate(ttx, tty).scale(scale));

    } catch (e) {
        console.error('法脈圖載入失敗:', e);
    }
}

// 追溯按钮
document.addEventListener('click', (e) => {
    if (e.target.id === 'lineage-expand-btn' && lnState.currentPerson) {
        if (lnState.lineageDepth < 4) {
            lnState.lineageDepth++;
            renderEgoGraph(lnState.currentPerson);
        }
    }
});

// 法脉全屏
const lineageContainer = document.getElementById('lineage-container');
if (lineageContainer) {
    lineageContainer.addEventListener('dblclick', (e) => {
        if (e.target.tagName === 'circle' || e.target.tagName === 'text') return;
        toggleLineageFullscreen();
    });
}

function toggleLineageFullscreen() {
    const panel = document.getElementById('panel-lineage');
    const mapPanel = document.getElementById('panel-map');
    lnState.lineageFullscreen = !lnState.lineageFullscreen;
    const btn = document.getElementById('lineage-fullscreen-btn');
    if (lnState.lineageFullscreen) {
        panel.classList.add('fullscreen');
        if (mapPanel) mapPanel.style.display = 'none';
        if (btn) btn.innerHTML = '<i data-lucide="minimize-2" style="width:12px;height:12px;vertical-align:middle"></i> 退出';
    } else {
        panel.classList.remove('fullscreen');
        if (mapPanel) mapPanel.style.display = '';
        if (btn) btn.innerHTML = '<i data-lucide="maximize-2" style="width:12px;height:12px;vertical-align:middle"></i> 全螢幕';
    }
    setTimeout(() => {
        if (lnState.currentPerson) renderEgoGraph(lnState.currentPerson);
        if (lnMap) lnMap.invalidateSize();
    }, 100);
    if (typeof lucide !== 'undefined') lucide.createIcons();
}
window.toggleLineageFullscreen = toggleLineageFullscreen;

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && lnState.lineageFullscreen) {
        toggleLineageFullscreen();
    }
    if (e.key === 'Escape' && lnState.mapFullscreen) {
        toggleMapFullscreen();
    }
});

// 地图全屏
function toggleMapFullscreen() {
    const panel = document.getElementById('panel-map');
    const lineagePanel = document.getElementById('panel-lineage');
    lnState.mapFullscreen = !lnState.mapFullscreen;
    const btn = document.getElementById('map-fullscreen-btn');
    if (lnState.mapFullscreen) {
        panel.classList.add('fullscreen');
        if (lineagePanel) lineagePanel.style.display = 'none';
        if (btn) btn.innerHTML = '<i data-lucide="minimize-2" style="width:12px;height:12px;vertical-align:middle"></i> 退出';
    } else {
        panel.classList.remove('fullscreen');
        if (lineagePanel) lineagePanel.style.display = '';
        if (btn) btn.innerHTML = '<i data-lucide="maximize-2" style="width:12px;height:12px;vertical-align:middle"></i> 全螢幕';
    }
    setTimeout(() => {
        if (lnMap) lnMap.invalidateSize();
        if (lnState.currentPerson) renderEgoGraph(lnState.currentPerson);
    }, 100);
    if (typeof lucide !== 'undefined') lucide.createIcons();
}
window.toggleMapFullscreen = toggleMapFullscreen;

// 双击地图容器全屏
const mapContainer = document.getElementById('map-container');
if (mapContainer) {
    mapContainer.addEventListener('dblclick', (e) => {
        // 不干扰 Leaflet 原生双击缩放
        if (e.target.classList.contains('ln-panel-body') || e.target.id === 'map-container') {
            toggleMapFullscreen();
        }
    });
}

// ============================================================
// 📜 编年时间轴 — 三层手风琴
// ============================================================
let chronicleData = null;
let currentMonkFilter = null;

async function initTimeline() {
    lnSetStatus('載入編年表...');
    try {
        const params = new URLSearchParams();
        if (currentMonkFilter) params.set('monk', currentMonkFilter);
        const qs = params.toString();
        const url = qs ? `/api/lineage/chronicle?${qs}` : '/api/lineage/chronicle';
        const data = await lnFetchJSON(url);
        chronicleData = data;
        renderChronicle(data);
        lnState.timelineInitialized = true;
    } catch (e) {
        lnSetStatus('編年表載入失敗: ' + e.message);
    }
}

// 僧俗过滤
window.setMonkFilter = function (value) {
    currentMonkFilter = value;
    document.querySelectorAll('#monk-all, #monk-monk, #monk-lay').forEach(btn => {
        btn.classList.remove('active');
    });
    if (value === 'monk') document.getElementById('monk-monk').classList.add('active');
    else if (value === 'lay') document.getElementById('monk-lay').classList.add('active');
    else document.getElementById('monk-all').classList.add('active');
    initTimeline();
};

function renderChronicle(data) {
    if (!data || data.length === 0) {
        document.getElementById('chronicle-container').innerHTML =
            '<div class="ln-empty-state"><div class="icon">📜</div><div>暫無編年資料</div></div>';
        return;
    }

    const dynastyGroups = {};
    const dynastyOrder = [];
    for (const period of data) {
        const dynasty = period.dynasty;
        if (!dynastyGroups[dynasty]) {
            dynastyGroups[dynasty] = {
                name: dynasty, periods: [], totalPersons: 0,
                startYear: period.start, endYear: period.end,
            };
            dynastyOrder.push(dynasty);
        }
        const g = dynastyGroups[dynasty];
        g.periods.push(period);
        g.totalPersons += period.person_count;
        g.endYear = Math.max(g.endYear, period.end);
        g.startYear = Math.min(g.startYear, period.start);
    }

    const container = document.getElementById('chronicle-container');
    let html = '';

    for (const dynasty of dynastyOrder) {
        const g = dynastyGroups[dynasty];
        const hasSubs = g.periods.length > 1;
        const yearLabel = formatYearRange(g.startYear, g.endYear);

        html += `<div class="chr-dynasty" data-dynasty="${dynasty}">`;
        html += `<div class="chr-dynasty-header" onclick="toggleDynasty('${dynasty}')">`;
        html += `  <span class="chr-toggle" id="chr-toggle-${CSS.escape(dynasty)}">▶</span>`;
        html += `  <span class="chr-dynasty-name">${dynasty}</span>`;
        html += `  <span class="chr-dynasty-years">${yearLabel}</span>`;
        html += `  <span class="chr-stat">`;
        html += `    <span><i data-lucide="users-round" class="ln-status-icon"></i> <span class="chr-stat-num">${g.totalPersons}</span></span>`;
        html += `  </span>`;
        html += `</div>`;

        html += `<div class="chr-dynasty-body" id="chr-body-${CSS.escape(dynasty)}">`;

        if (hasSubs) {
            for (const period of g.periods) {
                const subYears = formatYearRange(period.start, period.end);
                const subLabel = period.is_sub ? period.label.replace(dynasty + '·', '') : period.label;
                html += `<div class="chr-sub-row" onclick="toggleSubPeriod('${period.id}')">`;
                html += `  <span class="chr-toggle" id="chr-sub-toggle-${CSS.escape(period.id)}">▶</span>`;
                html += `  <span class="chr-sub-label">${subLabel}</span>`;
                html += `  <span class="chr-sub-years">${subYears}</span>`;
                html += `  <span class="chr-sub-stat">`;
                html += `    <span><i data-lucide="users-round" class="ln-status-icon"></i> ${period.person_count}</span>`;
                html += `  </span>`;
                html += `</div>`;
                html += renderDetailPanel(period);
            }
        } else {
            html += `<div class="chr-inline-detail">`;
            html += renderDetailContent(g.periods[0]);
            html += `</div>`;
        }

        html += `</div></div>`;
    }

    container.innerHTML = html;
    if (typeof lucide !== 'undefined') lucide.createIcons();

    const totalP = data.reduce((s, p) => s + p.person_count, 0);
    lnSetStatus('👇 請在編年表或上方搜尋列選擇人物'); // 更清晰的操作引导
}

function renderDetailPanel(period) {
    return `<div class="chr-detail-panel" id="chr-detail-${CSS.escape(period.id)}">`
        + renderDetailContent(period)
        + `</div>`;
}

function renderDetailContent(period) {
    let html = '';
    if (period.persons && period.persons.length > 0) {
        html += `<div class="chr-detail-section">`;
        html += `<div class="chr-list-grid">`;
        for (const p of period.persons) {
            const years = formatPersonYears(p.birth_year, p.death_year);
            html += `<div class="chr-person-item" data-person-id="${p.person_id}" onclick="lnSelectPerson('${p.person_id}')">`;
            html += `  <span class="chr-person-name">${p.name}</span>`;
            html += `  <span class="chr-person-years">${years}</span>`;
            if (p.sect) html += `<span class="chr-person-sect">${p.sect}</span>`;
            html += `</div>`;
        }
        html += `</div></div>`;
    }
    return html;
}

// 格式化年份
function formatYearRange(start, end) {
    if (start >= 9999) return '';
    const s = start < 0 ? `前${Math.abs(start)}` : `${start}`;
    const e = end < 0 ? `前${Math.abs(end)}` : `${end}`;
    return `${s}–${e}`;
}

function formatPersonYears(birth, death) {
    if (!birth && !death) return '';
    const b = birth ? (birth < 0 ? `前${Math.abs(birth)}` : birth) : '?';
    const d = death ? (death < 0 ? `前${Math.abs(death)}` : death) : '?';
    return `${b}–${d}`;
}

// 展开/折叠
window.toggleDynasty = function (dynasty) {
    const body = document.getElementById(`chr-body-${CSS.escape(dynasty)}`);
    const toggle = document.getElementById(`chr-toggle-${CSS.escape(dynasty)}`);
    const header = toggle.closest('.chr-dynasty-header');
    body.classList.toggle('open');
    toggle.classList.toggle('open');
    header.classList.toggle('open');
};

window.toggleSubPeriod = function (periodId) {
    const detail = document.getElementById(`chr-detail-${CSS.escape(periodId)}`);
    const toggle = document.getElementById(`chr-sub-toggle-${CSS.escape(periodId)}`);
    const row = toggle.closest('.chr-sub-row');
    detail.classList.toggle('open');
    toggle.classList.toggle('open');
    row.classList.toggle('open');
};

// 高亮联动
function highlightTimeline(personId) {
    if (!chronicleData) return;
    document.querySelectorAll('.chr-person-item.highlighted').forEach(el =>
        el.classList.remove('highlighted')
    );
    const el = document.querySelector(`.chr-person-item[data-person-id="${personId}"]`);
    if (el) {
        el.classList.add('highlighted');
        const dynastyBody = el.closest('.chr-dynasty-body');
        if (dynastyBody && !dynastyBody.classList.contains('open')) {
            const dynasty = dynastyBody.closest('.chr-dynasty');
            const dName = dynasty.dataset.dynasty;
            toggleDynasty(dName);
        }
        const detailPanel = el.closest('.chr-detail-panel');
        if (detailPanel && !detailPanel.classList.contains('open')) {
            const periodId = detailPanel.id.replace('chr-detail-', '');
            toggleSubPeriod(periodId);
        }
        setTimeout(() => {
            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }, 100);
    }
}

// ============================================================
// 🗺️ 行迹视图 — Leaflet
// ============================================================
let lnMap = null;
let lnTileLayer = null;
let originLayer = null;
let templeLayer = null;
let mountainLayer = null;
let personMarker = null;

// 根据当前主题选择底图模式 (light/dark)
function getMapThemeMode() {
    const isLight = document.body.classList.contains('theme-light')
        || document.documentElement.classList.contains('theme-light');
    return isLight ? 'light' : 'dark';
}

// 在线瓦片 URL 模板
function getOnlineTileUrl(mode) {
    return mode === 'light'
        ? 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png'
        : 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png';
}

// 本地瓦片 URL 模板（由 FastAPI /tiles 静态路由提供）
function getLocalTileUrl(mode) {
    return '/tiles/' + mode + '/{z}/{x}/{y}.png';
}

// 创建优先本地、回退在线的 TileLayer
function createOfflineFirstTileLayer(mode) {
    const localTemplate = getLocalTileUrl(mode);
    const onlineTemplate = getOnlineTileUrl(mode);

    return L.TileLayer.extend({
        createTile: function (coords, done) {
            var tile = document.createElement('img');
            tile.alt = '';
            tile.setAttribute('role', 'presentation');

            // 构建本地 URL
            var localUrl = localTemplate
                .replace('{z}', coords.z)
                .replace('{x}', coords.x)
                .replace('{y}', coords.y);

            // 构建在线 URL
            var subdomains = 'abcd';
            var s = subdomains[(coords.x + coords.y) % subdomains.length];
            var onlineUrl = onlineTemplate
                .replace('{s}', s)
                .replace('{z}', coords.z)
                .replace('{x}', coords.x)
                .replace('{y}', coords.y);

            // 先尝试本地
            tile.onload = function () { done(null, tile); };
            tile.onerror = function () {
                // 本地失败，回退到在线
                tile.onerror = function () { done(new Error('tile load failed'), tile); };
                tile.src = onlineUrl;
            };
            tile.src = localUrl;
            return tile;
        }
    });
}

// 当前使用的 TileLayer 类（缓存）
var _currentTileMode = null;

// 切换底图（主题变化时调用）
function updateMapTile() {
    if (!lnMap) return;
    var mode = getMapThemeMode();
    if (mode === _currentTileMode) return;
    _currentTileMode = mode;
    if (lnTileLayer) lnMap.removeLayer(lnTileLayer);
    var TileClass = createOfflineFirstTileLayer(mode);
    lnTileLayer = new TileClass(getLocalTileUrl(mode), {
        maxZoom: 19,
        attribution: '© <a href="https://carto.com/">CARTO</a> © <a href="https://www.openstreetmap.org/copyright">OSM</a>',
    }).addTo(lnMap);
}
window.updateMapTile = updateMapTile;

async function initMap() {
    lnSetStatus('載入地圖...');
    try {
        const container = document.getElementById('map-container');
        if (!container) return;

        lnMap = L.map(container, {
            center: [30, 110],
            zoom: 5,
            zoomControl: true,
        });

        var initMode = getMapThemeMode();
        _currentTileMode = initMode;
        var TileClass = createOfflineFirstTileLayer(initMode);
        lnTileLayer = new TileClass(getLocalTileUrl(initMode), {
            maxZoom: 19,
            attribution: '© <a href="https://carto.com/">CARTO</a> © <a href="https://www.openstreetmap.org/copyright">OSM</a>',
        }).addTo(lnMap);

        originLayer = L.layerGroup().addTo(lnMap);
        templeLayer = L.markerClusterGroup({
            maxClusterRadius: 40,
            iconCreateFunction: function (cluster) {
                const count = cluster.getChildCount();
                let size = 'small';
                if (count > 50) size = 'large';
                else if (count > 10) size = 'medium';
                return L.divIcon({
                    html: `<div><span>${count}</span></div>`,
                    className: `marker-cluster marker-cluster-${size}`,
                    iconSize: L.point(40, 40),
                });
            },
        }).addTo(lnMap);
        mountainLayer = L.layerGroup().addTo(lnMap);

        lnState.mapInitialized = true;
        setTimeout(() => lnMap.invalidateSize(), 300);
    } catch (e) {
        lnSetStatus('地圖載入失敗: ' + e.message);
    }
}

async function highlightMap(personId) {
    if (!lnMap || !lnState.mapInitialized) return;

    if (personMarker) {
        lnMap.removeLayer(personMarker);
        personMarker = null;
    }

    try {
        const places = await lnFetchJSON(`/api/lineage/person_places/${personId}`);
        if (places.length === 0) return;

        const personName = lnState.currentPersonData ? lnState.currentPersonData.name : '';
        personMarker = L.layerGroup().addTo(lnMap);

        const bounds = L.latLngBounds();
        places.forEach(p => {
            if (!p.latitude || !p.longitude) return;
            const marker = L.marker([p.latitude, p.longitude], {
                icon: L.divIcon({
                    html: '📍',
                    className: '',
                    iconSize: [24, 24],
                    iconAnchor: [12, 24],
                }),
            }).bindPopup(
                `<b>${p.name_zh}</b>${p.district ? '<br><span style="color:#9aa5b4;font-size:11px">' + p.district + '</span>' : ''}<br>📍 ${personName || '人物'}籍貫`
            );
            personMarker.addLayer(marker);
            bounds.extend([p.latitude, p.longitude]);
        });

        if (places.length > 1 && bounds.isValid()) {
            lnMap.fitBounds(bounds, { padding: [40, 40], maxZoom: 10, animate: true });
        } else {
            const p = places[0];
            lnMap.flyTo([p.latitude, p.longitude], 8, { animate: true, duration: 1 });
        }
        personMarker.getLayers()[0]?.openPopup();
    } catch (e) { /* 无籍贯数据 */ }
}
window.highlightMap = highlightMap;

// ============================================================
// 加载统计数据
// ============================================================
async function loadStats() {
    try {
        const stats = await lnFetchJSON('/api/lineage/stats');
        document.getElementById('ln-stat-persons').textContent = stats.persons || 0;
        document.getElementById('ln-stat-edges').textContent = stats.edges || 0;
        document.getElementById('ln-stat-places').textContent = stats.places || 0;
        document.getElementById('ln-stat-scriptures').textContent = stats.scriptures || 0;
    } catch (e) { /* 忽略 */ }
}

// ============================================================
// 初始化：四面板同时加载 + Split.js
// ============================================================
function initLineageDashboard() {
    // 确保 section 可见时才初始化
    const section = document.getElementById('lineage-section');
    if (!section) return;

    // Split.js：上下分割（详情 40% / 双图 60%）
    if (typeof Split !== 'undefined') {
        Split(['#panel-detail', '.ln-bottom-split'], {
            direction: 'vertical',
            sizes: [40, 60],
            minSize: [120, 200],
            gutterSize: 6,
        });
        // Split.js：左右分割（法脉 50% / 地图 50%）
        Split(['#panel-lineage', '#panel-map'], {
            sizes: [50, 50],
            minSize: [200, 200],
            gutterSize: 6,
        });
    }

    // 加载编年表
    initTimeline();
    // 加载地图
    initMap();
    // 加载统计
    loadStats();
    // 初始化 Lucide 图标
    if (typeof lucide !== 'undefined') lucide.createIcons();
}

// 窗口加载后初始化
window.addEventListener('load', () => {
    initLineageDashboard();

    // URL hash 自动选人：#person=A001583
    const hash = window.location.hash;
    if (hash.startsWith('#person=')) {
        const personId = hash.replace('#person=', '');
        if (personId) {
            // 滚动到「祖师」区域
            const section = document.getElementById('lineage-section');
            if (section) section.scrollIntoView({ behavior: 'smooth' });
            // 等面板初始化后再选人
            setTimeout(() => lnSelectPerson(personId), 800);
        }
    }
});

// 窗口大小变化
window.addEventListener('resize', () => {
    if (lnMap) lnMap.invalidateSize();
    if (lnState.currentPerson) renderEgoGraph(lnState.currentPerson);
});
