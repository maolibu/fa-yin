/**
 * 法印對照 50_reader+ — 前端交互
 * Alpine.js 組件：導航欄搜索 + 首頁搜索 + 收藏夾案頭
 */

/* ─── 導航欄全局搜索組件 ──────────────────────────────────── */
function navSearchApp() {
    return {
        query: '',
        results: [],
        titleResults: [],
        fulltextResults: [],
        showResults: false,
        loading: false,

        async doSearch() {
            const q = this.query.trim();
            if (q.length === 0) {
                this.results = [];
                this.titleResults = [];
                this.fulltextResults = [];
                this.showResults = false;
                return;
            }
            this.loading = true;
            try {
                const lang = localStorage.getItem('reader_textVariant') === 'simplified' ? 'sc' : 'tc';
                const resp = await fetch(`/api/search?q=${encodeURIComponent(q)}&lang=${lang}`);
                if (resp.ok) {
                    this.results = await resp.json();
                    this.titleResults = this.results.filter(r => r.section === 'title');
                    this.fulltextResults = this.results.filter(r => r.section === 'fulltext');
                    this.showResults = true;
                }
            } catch (e) {
                console.error('導航搜索失敗:', e);
            } finally {
                this.loading = false;
            }
        }
    };
}

/* ─── 首頁搜索欄組件 ──────────────────────────────────────── */
function searchApp() {
    return {
        query: '',
        results: [],
        titleResults: [],
        fulltextResults: [],
        showResults: false,
        loading: false,

        async doSearch() {
            const q = this.query.trim();
            if (q.length === 0) {
                this.results = [];
                this.titleResults = [];
                this.fulltextResults = [];
                this.showResults = false;
                return;
            }

            this.loading = true;
            try {
                const lang = localStorage.getItem('reader_textVariant') === 'simplified' ? 'sc' : 'tc';
                const resp = await fetch(`/api/search?q=${encodeURIComponent(q)}&lang=${lang}`);
                if (resp.ok) {
                    this.results = await resp.json();
                    this.titleResults = this.results.filter(r => r.section === 'title');
                    this.fulltextResults = this.results.filter(r => r.section === 'fulltext');
                    this.showResults = true;
                }
            } catch (e) {
                console.error('搜索失敗:', e);
            } finally {
                this.loading = false;
            }
        }
    };
}


/* ─── 收藏夾案頭組件 ──────────────────────────────────────── */
function favoritesApp() {
    return {
        modules: [],
        loaded: false,
        editMode: false,        // 編輯模式

        // ── 新建分區彈窗 ──
        showNewModuleModal: false,
        newModule: { name: '', subtitle: '', color: 'bamboo' },
        colorOptions: [
            // 第一行
            { value: 'bamboo', label: '竹青', css: '#4a7c5c' },
            { value: 'ochre', label: '枯黃', css: '#8b7335' },
            { value: 'sandalwood', label: '檀色', css: '#8c5e3a' },
            { value: 'cloud', label: '雲峰', css: '#6b7a8a' },
            // 第二行
            { value: 'indigo', label: '靛藍', css: '#4a5c8a' },
            { value: 'crimson', label: '硃砂', css: '#8a4a4a' },
            { value: 'rosewood', label: '紫檀', css: '#6e4a6e' },
            { value: 'pine', label: '松煙', css: '#3d5c52' },
            // 第三行
            { value: 'celadon', label: '青瓷', css: '#4a7a7a' },
            { value: 'amber', label: '琥珀', css: '#8a6a2a' },
            { value: 'moonwhite', label: '月白', css: '#7a8590' },
            { value: 'rust', label: '鐵鏽', css: '#7a5040' },
        ],

        // ── 添加菜單 ──
        addMenuModule: null,    // 當前打開添加菜單的模塊索引

        // ── 新建文件夾 ──
        showFolderInput: null,  // 正在新建文件夾的模塊索引
        newFolderName: '',

        // ── 內聯編輯 ──
        editingId: null,        // 正在編輯的項目標識（如 'mod_0_name', 'folder_0_1_name'）
        editingValue: '',

        // ── 收藏彈窗 ──
        showFavModal: false,
        favSearchQuery: '',
        favSearchResults: [],
        favSearchLoading: false,
        favTargetModule: null,  // 模塊索引
        favTargetFolder: null,  // 文件夾索引（null = 直接添加到模塊）

        // ── Toast ──
        toastMsg: '',
        toastVisible: false,

        /* ═══ 初始化與基礎 ═══ */

        async init() {
            try {
                const resp = await fetch('/api/favorites');
                if (resp.ok) {
                    this.modules = await resp.json();
                }
            } catch (e) {
                console.error('加載收藏夾失敗:', e);
            }
            this.loaded = true;
        },

        toggleModuleCollapse(index) {
            // 如果舊數據沒有 collapsed 屬性，默認認為是 false（展開）
            const isCollapsed = this.modules[index].collapsed === true;
            this.modules[index].collapsed = !isCollapsed;
            this.save();
        },

        toggleFolderCollapse(moduleIndex, folderIndex) {
            const folder = this.modules[moduleIndex].children[folderIndex];
            if (!folder || folder.type !== 'folder') return;
            folder.collapsed = !(folder.collapsed === true);
            this.save();
        },


        genId(prefix) {
            return prefix + '_' + Date.now().toString(36);
        },

        showToast(msg) {
            this.toastMsg = msg;
            this.toastVisible = true;
            setTimeout(() => { this.toastVisible = false; }, 2000);
        },

        /* ═══ 保存 ═══ */

        async save() {
            try {
                const resp = await fetch('/api/favorites', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.modules),
                });
                if (resp.ok) {
                    console.log('收藏夾已保存');
                }
            } catch (e) {
                console.error('保存失敗:', e);
            }
        },

        /* ═══ 新建分區（模塊） ═══ */

        openNewModuleModal() {
            this.newModule = { name: '', subtitle: '', color: 'bamboo' };
            this.showNewModuleModal = true;
            // 聚焦輸入框
            this.$nextTick(() => {
                const input = document.getElementById('new-module-name-input');
                if (input) input.focus();
            });
        },

        createModule() {
            const name = this.newModule.name.trim();
            if (!name) return;
            this.modules.unshift({
                type: 'module',
                id: this.genId('mod'),
                name: name,
                subtitle: this.newModule.subtitle.trim(),
                color: this.newModule.color,
                visible: true,
                collapsed: false,
                children: [],
            });
            this.showNewModuleModal = false;
            this.save();
            this.showToast('已創建書架「' + name + '」');
        },

        /* ═══ 刪除模塊 ═══ */

        deleteModule(index) {
            const name = this.modules[index].name;
            if (!this._confirm('確定刪除書架「' + name + '」？')) return;
            this.modules.splice(index, 1);
            this.save();
            this.showToast('已刪除書架「' + name + '」');
        },

        /* ═══ 隱藏/顯示模塊 ═══ */

        toggleModuleVisibility(index) {
            this.modules[index].visible = !this.modules[index].visible;
            this.save();
            const action = this.modules[index].visible ? '顯示' : '隱藏';
            this.showToast('已' + action + '「' + this.modules[index].name + '」');
        },

        /* ═══ 添加菜單 ═══ */

        openAddMenu(moduleIndex) {
            this.addMenuModule = this.addMenuModule === moduleIndex ? null : moduleIndex;
        },

        closeAddMenu() {
            this.addMenuModule = null;
        },

        /* ═══ 新建文件夾 ═══ */

        startNewFolder(moduleIndex) {
            this.addMenuModule = null;
            this.showFolderInput = moduleIndex;
            this.newFolderName = '';
            this.$nextTick(() => {
                const input = document.getElementById('new-folder-input-' + moduleIndex);
                if (input) input.focus();
            });
        },

        createFolder(moduleIndex) {
            const name = this.newFolderName.trim();
            if (!name) {
                this.showFolderInput = null;
                return;
            }
            this.modules[moduleIndex].children.push({
                type: 'folder',
                id: this.genId('folder'),
                name: name,
                children: [],
            });
            this.showFolderInput = null;
            this.newFolderName = '';
            this.save();
            this.showToast('已創建文件夾「' + name + '」');
        },

        cancelNewFolder() {
            this.showFolderInput = null;
            this.newFolderName = '';
        },

        /* ═══ 刪除文件夾 ═══ */

        deleteFolder(moduleIndex, childIndex) {
            const folder = this.modules[moduleIndex].children[childIndex];
            const name = folder.name;
            if (!this._confirm('確定刪除文件夾「' + name + '」及其中的所有經文？')) return;
            this.modules[moduleIndex].children.splice(childIndex, 1);
            this.save();
            this.showToast('已刪除文件夾「' + name + '」');
        },

        /* ═══ 刪除經文 ═══ */

        deleteSutra(moduleIndex, childIndex, sutraIndex) {
            // sutraIndex != null → 經文在文件夾中，childIndex 是文件夾索引
            // sutraIndex == null → 經文直接在模塊根級，childIndex 是經文索引
            if (sutraIndex !== undefined && sutraIndex !== null) {
                const folder = this.modules[moduleIndex].children[childIndex];
                const sutra = folder.children[sutraIndex];
                folder.children.splice(sutraIndex, 1);
                this.save();
                this.showToast('已移除「' + sutra.title + '」');
            } else {
                const sutra = this.modules[moduleIndex].children[childIndex];
                this.modules[moduleIndex].children.splice(childIndex, 1);
                this.save();
                this.showToast('已移除「' + sutra.title + '」');
            }
        },

        /* ═══ 內聯編輯（重命名） ═══ */

        startRename(editId, currentValue) {
            this.editingId = editId;
            this.editingValue = currentValue;
            this.$nextTick(() => {
                const input = document.getElementById('inline-edit-' + editId);
                if (input) { input.focus(); input.select(); }
            });
        },

        confirmRename(moduleIndex, childIndex, field) {
            const val = this.editingValue.trim();
            if (!val && field === 'name') {
                // 名稱不能為空，取消編輯
                this.cancelEdit();
                return;
            }
            if (childIndex !== undefined && childIndex !== null) {
                // 編輯文件夾名
                this.modules[moduleIndex].children[childIndex][field] = val;
            } else {
                // 編輯模塊名或副標語
                this.modules[moduleIndex][field] = val;
            }
            this.editingId = null;
            this.editingValue = '';
            this.save();
            this.showToast('已更新');
        },

        cancelEdit() {
            this.editingId = null;
            this.editingValue = '';
        },

        /* ═══ 收藏經文彈窗 ═══ */

        openFavModal(moduleIndex) {
            this.addMenuModule = null;
            this.favTargetModule = moduleIndex;
            this.favTargetFolder = null;
            this.favSearchQuery = '';
            this.favSearchResults = [];
            this.showFavModal = true;
            this.$nextTick(() => {
                const input = document.getElementById('fav-search-input');
                if (input) input.focus();
            });
        },

        async doFavSearch() {
            const q = this.favSearchQuery.trim();
            if (q.length === 0) {
                this.favSearchResults = [];
                return;
            }
            this.favSearchLoading = true;
            try {
                const resp = await fetch('/api/search?q=' + encodeURIComponent(q));
                if (resp.ok) {
                    this.favSearchResults = await resp.json();
                }
            } catch (e) {
                console.error('搜索失敗:', e);
            } finally {
                this.favSearchLoading = false;
            }
        },

        addSutraToTarget(sutra) {
            const mi = this.favTargetModule;
            if (mi === null || mi === undefined) return;
            const newItem = {
                type: 'sutra',
                id: sutra.sutra_id,
                title: sutra.title,
                juan: sutra.juan || null,
            };
            if (this.favTargetFolder !== null && this.favTargetFolder !== undefined) {
                const folder = this.modules[mi].children[this.favTargetFolder];
                // 檢查重複
                if (folder.children.some(c => c.id === sutra.sutra_id)) {
                    this.showToast('已存在「' + sutra.title + '」');
                    return;
                }
                folder.children.push(newItem);
            } else {
                // 直接加到模塊根級
                if (this.modules[mi].children.some(c => c.id === sutra.sutra_id && c.type === 'sutra')) {
                    this.showToast('已存在「' + sutra.title + '」');
                    return;
                }
                this.modules[mi].children.push(newItem);
            }
            this.save();
            this.showToast('已收藏「' + sutra.title + '」');
        },

        closeFavModal() {
            this.showFavModal = false;
            this.favSearchQuery = '';
            this.favSearchResults = [];
        },

        /* ═══ 編輯模式 ═══ */

        // 存儲 Sortable 實例，退出編輯時銷燬
        _sortableInstances: [],

        toggleEditMode() {
            this.editMode = !this.editMode;
            if (this.editMode) {
                // 進入編輯模式 → 初始化拖拽排序
                this.$nextTick(() => this._initSortables());
            } else {
                // 退出編輯模式 → 銷燬拖拽 & 清理狀態
                this._destroySortables();
                this.editingId = null;
                this.editingValue = '';
                this.showFolderInput = null;
                this.addMenuModule = null;
            }
        },

        /* ═══ 拖拽排序 ═══ */

        _initSortables() {
            if (typeof Sortable === 'undefined') return;
            this._destroySortables();

            const self = this;
            const ghostClass = 'sortable-ghost';
            const chosenClass = 'sortable-chosen';
            const dragClass = 'sortable-drag';

            // ① 模塊級排序（書架卡片之間拖拽）
            const grid = this.$refs.modulesGrid;
            if (grid) {
                this._sortableInstances.push(
                    Sortable.create(grid, {
                        animation: 200,
                        handle: '.module-header',
                        ghostClass, chosenClass, dragClass,
                        onEnd(evt) {
                            if (evt.oldIndex === evt.newIndex) return;
                            self._moveItem(self.modules, evt.oldIndex, evt.newIndex);
                            self.save();
                        },
                    })
                );
            }

            // ② 模塊內子項排序（文件夾 / 經文）
            grid?.querySelectorAll('.module-body').forEach((bodyEl) => {
                // 找到這個 module-body 對應的模塊索引
                const card = bodyEl.closest('.module-card');
                if (!card) return;
                const mi = parseInt(card.dataset.moduleIndex);
                if (isNaN(mi)) return;
                // 找到子項容器（template 渲染後的直接子 div 列表）
                // module-body 內的直接子元素包含 template 渲染的各個 div[data-child-index]
                this._sortableInstances.push(
                    Sortable.create(bodyEl, {
                        animation: 180,
                        ghostClass, chosenClass, dragClass,
                        draggable: '[data-child-index]',
                        filter: '.module-empty, .new-folder-row, .module-add-wrapper',
                        onEnd(evt) {
                            if (evt.oldIndex === evt.newIndex) return;
                            self._moveItem(self.modules[mi].children, evt.oldIndex, evt.newIndex);
                            self.save();
                        },
                    })
                );

                // ③ 文件夾內經文排序
                bodyEl.querySelectorAll('.folder-group').forEach((folderEl) => {
                    // 找到該文件夾在 children 中的位置
                    const childDiv = folderEl.closest('[data-child-index]');
                    if (!childDiv) return;
                    const ci = parseInt(childDiv.dataset.childIndex);
                    if (isNaN(ci) || !self.modules[mi].children[ci]) return;
                    // 經文列表容器是 folder-group 內 folder-header 之後的 div
                    const sutraContainer = folderEl.querySelector('div[x-show]');
                    if (!sutraContainer) return;
                    self._sortableInstances.push(
                        Sortable.create(sutraContainer, {
                            animation: 150,
                            ghostClass, chosenClass, dragClass,
                            draggable: '.sutra-item-row',
                            onEnd(evt) {
                                if (evt.oldIndex === evt.newIndex) return;
                                self._moveItem(self.modules[mi].children[ci].children, evt.oldIndex, evt.newIndex);
                                self.save();
                            },
                        })
                    );
                });
            });
        },

        _destroySortables() {
            this._sortableInstances.forEach(s => {
                try { s.destroy(); } catch (_) { /* 忽略 */ }
            });
            this._sortableInstances = [];
        },

        _moveItem(arr, from, to) {
            const item = arr.splice(from, 1)[0];
            arr.splice(to, 0, item);
        },

        /* ═══ 輔助：確認彈窗 ═══ */
        // 使用自定義 inline 確認而非 window.confirm
        // 出於簡潔考慮暫用 confirm()，後續可替換
        _confirm(msg) {
            return window.confirm(msg);
        },

        /* ═══ 計算已隱藏模塊數量 ═══ */

        get hiddenCount() {
            return this.modules.filter(m => !m.visible).length;
        },
    };
}


/* ─── 貝闕全藏目錄組件 ────────────────────────────────────── */
function catalogApp() {
    return {
        activeTab: 'bulei',    // 'bulei' 部類 | 'canon' 經藏
        treeData: [],          // 原始目錄樹
        filteredTree: [],      // 過濾後的目錄樹
        filterQuery: '',       // 搜索關鍵詞
        loaded: false,
        statText: '',
        openL1: new Set(),     // 展開的 L1 索引
        openSub: new Set(),    // 展開的子級 key（如 "0-1", "0-1-2"）

        async init() {
            await this.loadTree('bulei');
        },

        async switchTab(tab) {
            if (tab === this.activeTab && this.treeData.length > 0) return;
            this.activeTab = tab;
            this.filterQuery = '';
            this.openL1 = new Set();
            this.openSub = new Set();
            await this.loadTree(tab);
        },

        async loadTree(tab) {
            this.loaded = false;
            try {
                const url = tab === 'canon' ? '/api/nav/canon' : '/api/nav/bulei';
                const resp = await fetch(url);
                if (resp.ok) {
                    this.treeData = await resp.json();
                    this.filteredTree = this.treeData;
                    this.updateStat();
                }
            } catch (e) {
                console.error('加載目錄失敗:', e);
            }
            this.loaded = true;
        },

        toggleL1(index) {
            if (this.openL1.has(index)) {
                this.openL1.delete(index);
            } else {
                this.openL1.add(index);
            }
            // Alpine 需要重新賦值 Set 來觸發響應式
            this.openL1 = new Set(this.openL1);
        },

        toggleSub(key) {
            if (this.openSub.has(key)) {
                this.openSub.delete(key);
            } else {
                this.openSub.add(key);
            }
            this.openSub = new Set(this.openSub);
        },

        // 遞歸計算葉子節點數量
        countLeaves(node) {
            if (!node.children || node.children.length === 0) {
                return node.sutra_id ? 1 : 0;
            }
            let count = 0;
            for (const child of node.children) {
                count += this.countLeaves(child);
            }
            return count;
        },

        // 從 "T0001 長阿含經" 提取經名部分
        extractTitle(text) {
            if (!text) return '';
            const m = text.match(/^[A-Z]+[a-zA-Z]*\d+[a-zA-Z]*\s+(.+)/);
            return m ? m[1].trim() : text.trim();
        },

        // 搜索過濾
        applyFilter() {
            const q = this.filterQuery.trim();
            if (!q) {
                this.filteredTree = this.treeData;
                this.openL1 = new Set();
                this.openSub = new Set();
                this.updateStat();
                return;
            }
            // 繁簡兼容：生成簡體和繁體兩個搜索詞
            let q_sc = q.toLowerCase();
            let q_tc = q.toLowerCase();
            try {
                if (typeof OpenCC !== 'undefined') {
                    const cn2tw = OpenCC.Converter({ from: 'cn', to: 'tw' });
                    const tw2cn = OpenCC.Converter({ from: 'tw', to: 'cn' });
                    q_tc = cn2tw(q).toLowerCase();
                    q_sc = tw2cn(q).toLowerCase();
                }
            } catch (e) { /* OpenCC 不可用，只用原文匹配 */ }

            // 遞歸過濾：保留包含匹配葉子的分支
            this.filteredTree = this._filterNodes(this.treeData, q.toLowerCase(), q_sc, q_tc);
            // 自動展開所有匹配的分支
            this.openL1 = new Set();
            this.openSub = new Set();
            for (let i = 0; i < this.filteredTree.length; i++) {
                this.openL1.add(i);
                this._autoExpand(this.filteredTree[i], String(i));
            }
            this.updateStat();
        },

        _filterNodes(nodes, q, q_sc, q_tc) {
            const result = [];
            for (const node of nodes) {
                if (node.sutra_id && node.title) {
                    const titleLow = node.title.toLowerCase();
                    if (titleLow.includes(q) || titleLow.includes(q_sc) || titleLow.includes(q_tc)) {
                        result.push(node);
                        continue;
                    }
                }
                if (node.children && node.children.length > 0) {
                    const filteredChildren = this._filterNodes(node.children, q, q_sc, q_tc);
                    if (filteredChildren.length > 0) {
                        result.push({ ...node, children: filteredChildren });
                    }
                }
            }
            return result;
        },

        _autoExpand(node, prefix) {
            if (!node.children) return;
            for (let j = 0; j < node.children.length; j++) {
                const key = prefix + '-' + j;
                if (node.children[j].children && node.children[j].children.length > 0) {
                    this.openSub.add(key);
                    this._autoExpand(node.children[j], key);
                }
            }
        },

        updateStat() {
            let total = 0;
            const countAll = (nodes) => {
                for (const n of nodes) {
                    if (n.sutra_id) total++;
                    if (n.children) countAll(n.children);
                }
            };
            countAll(this.filteredTree);
            const tabName = this.activeTab === 'bulei' ? '部類' : '經藏';
            this.statText = this.filterQuery
                ? `${tabName}視圖 · 匹配 ${total} 部`
                : `${tabName}視圖 · 共 ${total} 部`;
        },
    };
}

