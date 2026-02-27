/**
 * 经文阅读器 — Alpine.js 组件
 *
 * 依赖 window.READER_CONFIG（由 Jinja2 模板注入）：
 *   { sutraId, sutraTitle, initialJuan, totalJuan }
 */

function readerApp() {
    var C = window.READER_CONFIG;

    // 读取对照列表
    var savedItems = [];
    try {
        var saved = localStorage.getItem('compare_' + C.sutraId);
        if (saved) savedItems = JSON.parse(saved);
    } catch (e) { }

    if (savedItems.length === 0 || savedItems[0].id !== C.sutraId) {
        savedItems = [
            { id: C.sutraId, title: C.sutraTitle, commentaries: [] }
        ].concat(
            savedItems.filter(function (x) { return x.id !== C.sutraId; })
        );
    }

    // 读取保存的设置
    var savedFontSize = localStorage.getItem('reader_fontSize') || '20';
    var savedLineHeight = localStorage.getItem('reader_lineHeight') || '2.0';
    var savedVariant = localStorage.getItem('reader_textVariant') || 'original';
    var savedFontStyle = localStorage.getItem('reader_fontStyle') || 'songti';
    var savedTheme = localStorage.getItem('reader_theme') || 'dark';
    var savedWritingMode = localStorage.getItem('reader_writingMode') || 'horizontal';

    return {
        currentJuan: C.initialJuan,
        totalJuan: C.totalJuan,
        sutraId: C.sutraId,
        sutraTitle: C.sutraTitle,
        activePanel: null,
        splitMode: false,
        themeMode: savedTheme,
        panelTitles: {
            'compare': '对照工作台',
            'person': '经文人物',
            'notes': '闪念笔记',
            'dict': '詞典查詢',
            'ai': 'AI 释义',
            'settings': '阅读设置'
        },

        // ═══ 设置相关 ═══
        fontSize: savedFontSize,
        lineHeight: savedLineHeight,
        textVariant: savedVariant,
        _originalHTML: null,
        _rightOriginalHTML: null,
        _occConverter: null,

        // ═══ 字体风格 ═══
        fontStyle: savedFontStyle,

        // ═══ 排版方向 ═══
        writingMode: savedWritingMode,

        // ═══ 分栏相关 ═══
        splitItem: null,
        splitJuan: 1,
        splitTotalJuans: [],
        _splitInstance: null,

        // ═══ 人物相关 ═══
        personsAuthored: [],
        personsMentioned: [],
        personsTextFound: [],
        personsLoading: false,
        _personsLoaded: false,
        personTab: 'left',  // 'left' 或 'right'
        rightPersonsAuthored: [],
        rightPersonsMentioned: [],
        rightPersonsTextFound: [],
        rightPersonsLoading: false,
        _rightPersonsSutraId: null,  // 已加载的右栏经文 ID（避免重复加载）

        // ═══ 笔记相关 ═══
        noteQuote: '',
        noteContent: '',
        noteSaveStatus: '',
        notesList: [],

        // ═══ 詞典相关 ═══
        dictQuery: '',
        dictResults: [],
        dictLoading: false,
        dictSearched: false,
        _lastDictQuery: '',        // 上次成功查询的词（避免重复请求）
        _dictDebounceTimer: null,  // 词典输入框防抖定时器

        // ═══ AI 释义 ═══
        aiProvider: localStorage.getItem('ai_provider') || 'deepseek',
        aiApiKey: localStorage.getItem('ai_apikey') || '',
        aiMode: 'translate',
        aiResult: '',
        aiLoading: false,
        aiError: '',
        aiSelectedText: '',
        aiQuestion: '',
        aiProviders: [],
        _aiAbortController: null,
        aiCustomUrl: localStorage.getItem('ai_custom_url') || '',
        aiCustomModel: localStorage.getItem('ai_custom_model') || '',

        init: function () {
            var self = this;
            // 从服务端加载偏好，合并到当前状态
            this._loadServerPreferences();

            this.applySettings();
            this._applyFontStyle();
            this._applyWritingMode();
            // 应用保存的主题
            if (this.themeMode === 'light') {
                document.body.classList.add('theme-light');
            }
            if (typeof OpenCC !== 'undefined') {
                this._occConverter = OpenCC.Converter({ from: 'tw', to: 'cn' });
            }
            if (this.textVariant === 'simplified') {
                document.addEventListener('htmx:afterSettle', function (e) {
                    if (e.detail.target && e.detail.target.id === 'reader-content') {
                        setTimeout(function () { self._convertToSimplified(); }, 50);
                    }
                });
                setTimeout(function () { self._convertToSimplified(); }, 200);
            }

            // 监听 HTMX 替换完成，为了竖排模式自动滚动到开头
            document.addEventListener('htmx:afterSettle', function (e) {
                if (self.writingMode === 'vertical') {
                    self._scrollVerticalToStart();
                }
            });
            // 监听选中文本 → 自动填入笔记引用 + 詞典查询 + AI 选中文本
            document.addEventListener('mouseup', function () {
                var sel = window.getSelection();
                if (sel && sel.toString().trim()) {
                    var leftPanel = document.getElementById('reader-content');
                    var rightPanel = document.getElementById('reader-right-content');
                    var inLeft = leftPanel && leftPanel.contains(sel.anchorNode);
                    var inRight = rightPanel && rightPanel.contains(sel.anchorNode);
                    if (inLeft || inRight) {
                        var text = sel.toString().trim().substring(0, 30);
                        self.noteQuote = sel.toString().trim().substring(0, 500);
                        // 自动填入詞典查询
                        if (text.length >= 1 && text.length <= 30) {
                            self.dictQuery = text;
                            // 取消输入框的 debounce 定时器，避免竞态
                            clearTimeout(self._dictDebounceTimer);
                            self.lookupDict();
                        }
                        // 自动填入 AI 选中文本
                        self.aiSelectedText = sel.toString().trim().substring(0, 2000);
                    }
                }
            });
            // 加载 AI 提供商列表
            this._loadAiProviders();
            // 加载今日笔记
            this._loadNotes();

            // 初始化 Lucide 图标（在 Alpine 完成 DOM 处理后执行）
            this.$nextTick(function () {
                if (typeof lucide !== 'undefined') lucide.createIcons();
            });
        },

        applySettings: function () {
            var content = document.getElementById('reader-content');
            if (content) {
                content.style.fontSize = this.fontSize + 'px';
                content.style.lineHeight = this.lineHeight;
            }
            // 右栏对照也同步字号和行距
            var rightContent = document.getElementById('reader-right-content');
            if (rightContent) {
                rightContent.style.fontSize = this.fontSize + 'px';
                rightContent.style.lineHeight = this.lineHeight;
            }
            this._saveSettings();
        },

        setTheme: function (mode) {
            this.themeMode = mode;
            if (mode === 'light') {
                document.body.classList.add('theme-light');
            } else {
                document.body.classList.remove('theme-light');
            }
            localStorage.setItem('reader_theme', mode);
            this._syncSettingsToServer();
            // 刷新 Lucide 图标以适配新颜色
            if (typeof lucide !== 'undefined') lucide.createIcons();
        },

        _saveSettings: function () {
            try {
                localStorage.setItem('reader_fontSize', this.fontSize);
                localStorage.setItem('reader_lineHeight', this.lineHeight);
                localStorage.setItem('reader_textVariant', this.textVariant);
                localStorage.setItem('reader_fontStyle', this.fontStyle);
                localStorage.setItem('reader_writingMode', this.writingMode);
            } catch (e) { }
            this._syncSettingsToServer();
        },

        // ═══ 字体切换 ═══
        setFontStyle: function (style) {
            this.fontStyle = style;
            this._applyFontStyle();
            this._saveSettings();
        },

        // ═══ 排版方向切换 ═══
        setWritingMode: function (mode) {
            this.writingMode = mode;
            this._applyWritingMode();
            this._saveSettings();
        },

        _applyWritingMode: function () {
            var layout = document.getElementById('reader-layout');
            if (!layout) return;
            if (this.writingMode === 'vertical') {
                layout.classList.add('writing-vertical');
                // 竖排模式：将滚动条定位到最右侧（经文开头）
                this._scrollVerticalToStart();
                // 竖排分栏：同步头部高度
                var self = this;
                setTimeout(function () { self._equalizeVerticalHeaders(); }, 100);
            } else {
                layout.classList.remove('writing-vertical');
                // 切回横排时清除右栏头部的固定高度
                var rh = document.querySelector('.reader-right-header');
                if (rh) rh.style.minHeight = '';
            }
        },

        _scrollVerticalToStart: function () {
            // 将某个元素的横向滚动条推到最右边（经文开头）
            function scrollToRight(el) {
                if (!el || el.scrollWidth <= el.clientWidth) return;
                el.scrollLeft = el.scrollWidth - el.clientWidth;
            }
            var self = this;
            function doScroll() {
                var layout = document.getElementById('reader-layout');
                if (!layout) return;
                if (self.splitMode) {
                    // 分栏+竖排： juan-body 是横向滚动容器
                    scrollToRight(document.getElementById('reader-content'));
                    scrollToRight(document.getElementById('reader-right-content'));
                } else {
                    // 单栏模式： reader-layout 作为滚动容器
                    scrollToRight(layout);
                }
            }
            setTimeout(doScroll, 50);
            // 兜底重试：应对字体加载或 HTMX 内容延迟
            setTimeout(doScroll, 500);
        },

        // 竖排分栏：同步左右栏头部高度，以左栏为准
        _equalizeVerticalHeaders: function () {
            var left = document.querySelector('.reader-sticky-top');
            var right = document.querySelector('.reader-right-header');
            if (!left || !right) return;
            // 先重置，再读取自然高度
            right.style.minHeight = '';
            var leftH = left.offsetHeight;
            right.style.minHeight = leftH + 'px';
        },

        // 分栏时：将指定栏滚动到垂直顶部（横排阅读用）
        scrollPanelToTop: function (side) {
            // 实际滚动容器是 .juan-body，不是面板容器
            var id = side === 'left' ? 'reader-content' : 'reader-right-content';
            var el = document.getElementById(id);
            if (el) el.scrollTop = 0;
        },

        // 分栏时：将指定栏滚动到经文开头（竖排阅读用，即最右侧）
        scrollPanelToStart: function (side) {
            // 竖排分栏：juan-body 是滚动容器
            var id = side === 'left' ? 'reader-content' : 'reader-right-content';
            var el = document.getElementById(id);
            if (el && el.scrollWidth > el.clientWidth) {
                el.scrollLeft = el.scrollWidth - el.clientWidth;
            }
        },

        _applyFontStyle: function () {
            var fontMap = {
                'songti': "'SourceHanSerif', 'WenJinMincho', serif",
                'jigmo': "'Jigmo', serif",
                'oldsong': "'NanoOldSong', 'Jigmo', serif"
            };
            var fontValue = fontMap[this.fontStyle] || fontMap['songti'];
            var content = document.getElementById('reader-content');
            if (content) content.style.fontFamily = fontValue;
            var rightContent = document.getElementById('reader-right-content');
            if (rightContent) rightContent.style.fontFamily = fontValue;
            // 经文标题跟随正文字体（含罕见字回退）
            var title = document.querySelector('.sutra-title');
            if (title) title.style.fontFamily = fontValue;
        },

        setTextVariant: function (variant) {
            if (variant === this.textVariant) return;
            this.textVariant = variant;
            this._saveSettings();
            if (variant === 'simplified') {
                this._convertToSimplified();
            } else {
                this._restoreOriginal();
            }
        },

        _convertToSimplified: function () {
            var converter = this._occConverter;
            if (!converter) return;

            // 转换指定容器内的文本
            function convertContainer(el) {
                var walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null, false);
                var node;
                while (node = walker.nextNode()) {
                    var text = node.textContent;
                    if (text.trim()) {
                        var converted = converter(text);
                        if (converted !== text) {
                            node.textContent = converted;
                        }
                    }
                }
            }

            // 左栏
            var content = document.getElementById('reader-content');
            if (content) {
                if (!this._originalHTML) {
                    this._originalHTML = content.innerHTML;
                }
                convertContainer(content);
            }

            // 右栏（对照）
            var rightContent = document.getElementById('reader-right-content');
            if (rightContent && rightContent.textContent.trim()) {
                if (!this._rightOriginalHTML) {
                    this._rightOriginalHTML = rightContent.innerHTML;
                }
                convertContainer(rightContent);
            }
        },

        _restoreOriginal: function () {
            // 左栏
            var content = document.getElementById('reader-content');
            if (content && this._originalHTML) {
                content.innerHTML = this._originalHTML;
                this._originalHTML = null;
            }
            // 右栏
            var rightContent = document.getElementById('reader-right-content');
            if (rightContent && this._rightOriginalHTML) {
                rightContent.innerHTML = this._rightOriginalHTML;
                this._rightOriginalHTML = null;
            }
        },

        resetSettings: function () {
            this.fontSize = '20';
            this.lineHeight = '2.0';
            this.fontStyle = 'songti';
            this.writingMode = 'horizontal';
            if (this.textVariant !== 'original') {
                this.textVariant = 'original';
                this._restoreOriginal();
            }
            this.setTheme('dark');
            this._applyFontStyle();
            this._applyWritingMode();
            this.applySettings();
        },

        // ═══ 对照相关 ═══
        compareItems: savedItems,
        addDialogOpen: false,
        addDialogType: '',
        addDialogTarget: -1,
        addSearchQuery: '',
        addSearchResults: [],

        togglePanel: function (name) {
            this.activePanel = this.activePanel === name ? null : name;
            if (this.activePanel === null) {
                this.addDialogOpen = false;
            }
            // 首次打开人物面板时加载数据
            if (name === 'person' && !this._personsLoaded) {
                this._loadPersons();
            }
            // 分栏模式下切换到人物面板时，自动加载右栏人物
            if (name === 'person' && this.splitMode && this.splitItem) {
                this._loadRightPersons();
            }
            // 重新渲染 Lucide 图标（面板内动态内容）
            var self = this;
            this.$nextTick(function () {
                if (typeof lucide !== 'undefined') lucide.createIcons();
            });
        },

        _loadPersons: function () {
            this.personsLoading = true;
            this._personsLoaded = true;
            var self = this;
            fetch('/api/persons/' + this.sutraId)
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    self.personsAuthored = data.authored || [];
                    self.personsMentioned = data.mentioned || [];
                    self.personsTextFound = data.text_found || [];
                    self.personsLoading = false;
                })
                .catch(function () {
                    self.personsLoading = false;
                });
        },

        _loadRightPersons: function () {
            if (!this.splitItem) return;
            var rightId = this.splitItem.id;
            // 避免重复加载同一经文
            if (this._rightPersonsSutraId === rightId) return;
            this.rightPersonsLoading = true;
            this._rightPersonsSutraId = rightId;
            var self = this;
            fetch('/api/persons/' + rightId)
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    self.rightPersonsAuthored = data.authored || [];
                    self.rightPersonsMentioned = data.mentioned || [];
                    self.rightPersonsTextFound = data.text_found || [];
                    self.rightPersonsLoading = false;
                })
                .catch(function () {
                    self.rightPersonsLoading = false;
                });
        },

        setPersonTab: function (tab) {
            this.personTab = tab;
            if (tab === 'right' && this.splitItem) {
                this._loadRightPersons();
            }
        },

        showAddDialog: function (type, targetIdx) {
            this.addDialogType = type;
            this.addDialogTarget = targetIdx;
            this.addDialogOpen = true;
            this.addSearchQuery = '';
            this.addSearchResults = [];
            var self = this;
            setTimeout(function () {
                var input = self.$refs.addSearchInput;
                if (input) input.focus();
            }, 100);
        },

        searchSutras: function () {
            var q = this.addSearchQuery.trim();
            if (q.length < 1) { this.addSearchResults = []; return; }
            var self = this;
            fetch('/api/search_sutra?q=' + encodeURIComponent(q))
                .then(function (r) { return r.json(); })
                .then(function (data) { self.addSearchResults = data.results || []; })
                .catch(function () { self.addSearchResults = []; });
        },

        addFromSearch: function (result) {
            if (this.addDialogType === 'sutra') {
                var exists = this.compareItems.some(function (x) { return x.id === result.id; });
                if (!exists) {
                    this.compareItems.push({ id: result.id, title: result.title, commentaries: [] });
                }
            } else {
                var target = this.compareItems[this.addDialogTarget];
                if (target) {
                    if (!target.commentaries) target.commentaries = [];
                    var exists2 = target.commentaries.some(function (x) { return x.id === result.id; });
                    if (!exists2) {
                        target.commentaries.push({ id: result.id, title: result.title });
                    }
                }
            }
            this.addDialogOpen = false;
            this.addSearchQuery = '';
            this.addSearchResults = [];
            this._saveCompareState();
            // 重新渲染 Lucide 图标（新增的 DOM 元素需要处理）
            var self = this;
            this.$nextTick(function () { if (typeof lucide !== 'undefined') lucide.createIcons(); });
        },

        removeCompareItem: function (idx) {
            this.compareItems.splice(idx, 1);
            this._saveCompareState();
        },

        removeCommentary: function (itemIdx, commentaryIdx) {
            var item = this.compareItems[itemIdx];
            if (item && item.commentaries) {
                item.commentaries.splice(commentaryIdx, 1);
                this._saveCompareState();
                this.$nextTick(function () { if (typeof lucide !== 'undefined') lucide.createIcons(); });
            }
        },

        loadInRightPanel: function (item) {
            this.splitItem = item;
            this.splitJuan = 1;
            this.splitMode = true;
            this.activePanel = null;
            var self = this;
            // 获取右栏经文总卷数
            fetch('/api/search_sutra?q=' + encodeURIComponent(item.id))
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    var found = (data.results || []).find(function (x) { return x.id === item.id; });
                    var total = found && found.total_juan ? found.total_juan : 1;
                    self.splitTotalJuans = [];
                    for (var i = 1; i <= total; i++) self.splitTotalJuans.push(i);
                    self.loadSplitJuan();
                })
                .catch(function () {
                    self.splitTotalJuans = [1];
                    self.loadSplitJuan();
                });
            // 初始化 Split.js
            setTimeout(function () {
                if (self._splitInstance) self._splitInstance.destroy();
                if (typeof Split !== 'undefined') {
                    self._splitInstance = Split(['#reader-left', '#reader-right'], {
                        sizes: [50, 50],
                        minSize: 300,
                        gutterSize: 6,
                        onDragEnd: function () { self._equalizeVerticalHeaders(); },
                        direction: 'horizontal'
                    });
                }
                // 分栏初始化后同步头部高度
                setTimeout(function () { self._equalizeVerticalHeaders(); }, 200);
            }, 100);
        },

        loadSplitJuan: function () {
            if (!this.splitItem) return;
            var url = '/api/content/' + this.splitItem.id + '/' + this.splitJuan;
            htmx.ajax('GET', url, '#reader-right-content');
        },

        prevSplitJuan: function () {
            if (this.splitJuan > 1) {
                this.splitJuan = parseInt(this.splitJuan) - 1;
                this.loadSplitJuan();
            }
        },

        nextSplitJuan: function () {
            if (this.splitJuan < this.splitTotalJuans.length) {
                this.splitJuan = parseInt(this.splitJuan) + 1;
                this.loadSplitJuan();
            }
        },

        closeSplit: function () {
            this.splitMode = false;
            this.splitItem = null;
            this.personTab = 'left';  // 关闭分栏时切回左栏
            if (this._splitInstance) {
                this._splitInstance.destroy();
                this._splitInstance = null;
            }
            // 清理 Split.js 残留样式
            var left = document.getElementById('reader-left');
            var right = document.getElementById('reader-right');
            if (left) { left.style.width = ''; left.style.flex = ''; }
            if (right) { right.style.width = ''; right.style.flex = ''; }
        },

        _saveCompareState: function () {
            try {
                localStorage.setItem('compare_' + this.sutraId, JSON.stringify(this.compareItems));
            } catch (e) { }
            this._syncCompareToServer();
            // 同步注疏到 commentary API
            this._syncCommentaryToServer();
        },

        // ═══ 詞典功能 ═══
        lookupDict: function () {
            var q = (this.dictQuery || '').trim();
            if (!q) return;
            // 与上次查询相同且已有结果，直接跳过
            if (q === this._lastDictQuery && this.dictResults.length > 0) return;
            var self = this;
            this.dictLoading = true;
            this.dictSearched = true;
            fetch('/api/dict/lookup?q=' + encodeURIComponent(q))
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    self.dictResults = data.results || [];
                    self.dictLoading = false;
                    self._lastDictQuery = q;
                })
                .catch(function () {
                    self.dictResults = [];
                    self.dictLoading = false;
                });
        },

        // ═══ AI 释义功能 ═══
        _loadAiProviders: function () {
            var self = this;
            fetch('/api/ai/providers')
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    self.aiProviders = data.providers || [];
                })
                .catch(function () { self.aiProviders = []; });
        },

        setAiMode: function (mode) {
            this.aiMode = mode;
            this.aiResult = '';
            this.aiError = '';
        },

        askAI: function () {
            var text = (this.aiSelectedText || '').trim();
            // 白话翻译和名相释义需要选中文字，自由问答可以不选
            if (!text && this.aiMode !== 'ask') {
                this.aiError = '请先在经文中选中文字';
                return;
            }
            if (this.aiMode === 'ask' && !text && !(this.aiQuestion || '').trim()) {
                this.aiError = '请输入问题，或先选中经文';
                return;
            }

            // 校验 API Key（Ollama 除外）
            var providerInfo = null;
            for (var i = 0; i < this.aiProviders.length; i++) {
                if (this.aiProviders[i].id === this.aiProvider) {
                    providerInfo = this.aiProviders[i];
                    break;
                }
            }
            if (providerInfo && !providerInfo.no_key && !providerInfo.has_server_key && !this.aiApiKey.trim()) {
                this.aiError = '请先在设置面板中填入 ' + (providerInfo ? providerInfo.name : '') + ' 的 API Key';
                return;
            }

            // 中止之前的请求
            if (this._aiAbortController) {
                this._aiAbortController.abort();
            }
            this._aiAbortController = new AbortController();

            this.aiLoading = true;
            this.aiResult = '';
            this.aiError = '';

            var self = this;
            var body = {
                text: text,
                mode: this.aiMode,
                provider: this.aiProvider,
                api_key: this.aiApiKey || '',
                question: this.aiQuestion || '',
                sutra_title: C.sutraTitle || '',
                custom_url: this.aiCustomUrl || '',
                custom_model: this.aiCustomModel || '',
            };

            fetch('/api/ai/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
                signal: this._aiAbortController.signal,
            })
                .then(function (response) {
                    var reader = response.body.getReader();
                    var decoder = new TextDecoder();
                    var buffer = '';

                    function processStream() {
                        return reader.read().then(function (result) {
                            if (result.done) {
                                self.aiLoading = false;
                                return;
                            }
                            buffer += decoder.decode(result.value, { stream: true });
                            var lines = buffer.split('\n');
                            buffer = lines.pop() || '';
                            for (var i = 0; i < lines.length; i++) {
                                var line = lines[i].trim();
                                if (!line.startsWith('data: ')) continue;
                                var data = line.substring(6);
                                if (data === '[DONE]') {
                                    self.aiLoading = false;
                                    return;
                                }
                                try {
                                    var parsed = JSON.parse(data);
                                    if (parsed.error) {
                                        self.aiError = parsed.error;
                                        self.aiLoading = false;
                                        return;
                                    }
                                    if (parsed.content) {
                                        self.aiResult += parsed.content;
                                    }
                                } catch (e) { /* 忽略解析错误 */ }
                            }
                            return processStream();
                        });
                    }
                    return processStream();
                })
                .catch(function (err) {
                    if (err.name !== 'AbortError') {
                        self.aiError = '网络错误: ' + err.message;
                    }
                    self.aiLoading = false;
                });
        },

        stopAI: function () {
            if (this._aiAbortController) {
                this._aiAbortController.abort();
                this._aiAbortController = null;
            }
            this.aiLoading = false;
        },

        saveAiSettings: function () {
            try {
                localStorage.setItem('ai_provider', this.aiProvider);
                localStorage.setItem('ai_apikey', this.aiApiKey);
                localStorage.setItem('ai_custom_url', this.aiCustomUrl);
                localStorage.setItem('ai_custom_model', this.aiCustomModel);
            } catch (e) { }
            // AI 设置同步到服务端（不含 API Key）
            this._syncAiToServer();
        },

        // ═══ 服务端偏好同步 ═══

        _loadServerPreferences: function () {
            // 从服务端加载偏好，覆盖 localStorage 的默认值
            var self = this;
            fetch('/api/user_data/preferences')
                .then(function (r) { return r.json(); })
                .then(function (prefs) {
                    if (!prefs || typeof prefs !== 'object') return;
                    var changed = false;

                    // 合并阅读设置
                    if (prefs.reader) {
                        var r = prefs.reader;
                        if (r.fontSize && r.fontSize !== self.fontSize) { self.fontSize = r.fontSize; changed = true; }
                        if (r.lineHeight && r.lineHeight !== self.lineHeight) { self.lineHeight = r.lineHeight; changed = true; }
                        if (r.textVariant && r.textVariant !== self.textVariant) { self.textVariant = r.textVariant; changed = true; }
                        if (r.fontStyle && r.fontStyle !== self.fontStyle) { self.fontStyle = r.fontStyle; changed = true; }
                        if (r.writingMode && r.writingMode !== self.writingMode) { self.writingMode = r.writingMode; changed = true; }
                        if (r.theme && r.theme !== self.themeMode) { self.themeMode = r.theme; self.setTheme(r.theme); }
                    }

                    // 合并 AI 设置（不含 API Key）
                    if (prefs.ai) {
                        if (prefs.ai.provider) self.aiProvider = prefs.ai.provider;
                        if (prefs.ai.customUrl) self.aiCustomUrl = prefs.ai.customUrl;
                        if (prefs.ai.customModel) self.aiCustomModel = prefs.ai.customModel;
                    }

                    // 合并对照经文配置
                    var hasUserConfig = false;
                    if (prefs.compare && prefs.compare[self.sutraId]) {
                        var serverItems = prefs.compare[self.sutraId];
                        // 服务端数据优先（如果 localStorage 是默认空状态）
                        var localSaved = localStorage.getItem('compare_' + self.sutraId);
                        if (!localSaved && serverItems.length > 0) {
                            self.compareItems = serverItems;
                        }
                        hasUserConfig = true;
                    }

                    // 无用户自定义配置时，自动加载同部类注疏
                    var localSaved2 = localStorage.getItem('compare_' + self.sutraId);
                    if (!hasUserConfig && !localSaved2) {
                        self._loadBuleiCommentaries();
                    }

                    if (changed) {
                        self.applySettings();
                        self._applyFontStyle();
                        self._applyWritingMode();
                        // 同步回 localStorage
                        try {
                            localStorage.setItem('reader_fontSize', self.fontSize);
                            localStorage.setItem('reader_lineHeight', self.lineHeight);
                            localStorage.setItem('reader_textVariant', self.textVariant);
                            localStorage.setItem('reader_fontStyle', self.fontStyle);
                            localStorage.setItem('reader_theme', self.themeMode);
                            localStorage.setItem('reader_writingMode', self.writingMode);
                        } catch (e) { }
                    }
                })
                .catch(function () { /* 离线模式：忽略，使用 localStorage */ });
        },

        // 防抖定时器
        _syncTimer: null,

        _syncSettingsToServer: function () {
            // 防抖：300ms 内多次调用只执行最后一次
            var self = this;
            clearTimeout(this._syncTimer);
            this._syncTimer = setTimeout(function () {
                var data = {
                    reader: {
                        fontSize: self.fontSize,
                        lineHeight: self.lineHeight,
                        textVariant: self.textVariant,
                        fontStyle: self.fontStyle,
                        theme: self.themeMode,
                        writingMode: self.writingMode
                    }
                };
                fetch('/api/user_data/preferences', {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                }).catch(function () { });
            }, 300);
        },

        _syncCompareToServer: function () {
            var self = this;
            // 构建 compare 数据（以 sutraId 为 key）
            var compareData = {};
            compareData[this.sutraId] = this.compareItems;
            // 需要合并已有的其他经文的对照配置
            fetch('/api/user_data/preferences')
                .then(function (r) { return r.json(); })
                .then(function (prefs) {
                    var existingCompare = (prefs && prefs.compare) || {};
                    existingCompare[self.sutraId] = self.compareItems;
                    fetch('/api/user_data/preferences', {
                        method: 'PATCH',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ compare: existingCompare })
                    }).catch(function () { });
                })
                .catch(function () {
                    // 无法读取已有数据，直接写入当前经文的
                    fetch('/api/user_data/preferences', {
                        method: 'PATCH',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ compare: compareData })
                    }).catch(function () { });
                });
        },

        _syncAiToServer: function () {
            // 同步 AI 设置（不含 API Key）
            var data = {
                ai: {
                    provider: this.aiProvider,
                    customUrl: this.aiCustomUrl,
                    customModel: this.aiCustomModel
                }
            };
            fetch('/api/user_data/preferences', {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            }).catch(function () { });
        },

        // ═══ 自动加载注疏映射 ═══

        _loadBuleiCommentaries: function () {
            // 从 commentary API 加载注疏映射（优先用户自定义，回退默认）
            var self = this;
            fetch('/api/commentary/' + this.sutraId)
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data || !data.commentaries || data.commentaries.length === 0) return;
                    // 填入 compareItems[0] 的 commentaries
                    if (self.compareItems.length > 0 && self.compareItems[0].id === self.sutraId) {
                        if (!self.compareItems[0].commentaries || self.compareItems[0].commentaries.length === 0) {
                            self.compareItems[0].commentaries = data.commentaries;
                        }
                    }
                })
                .catch(function () { /* 忽略错误 */ });
        },

        _syncCommentaryToServer: function () {
            // 将当前经文的注疏列表同步到 commentary API
            if (!this.compareItems[0] || this.compareItems[0].id !== this.sutraId) return;
            var self = this;
            var body = {
                title: this.compareItems[0].title || this.sutraTitle,
                commentaries: this.compareItems[0].commentaries || []
            };
            fetch('/api/commentary/' + this.sutraId, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            }).catch(function () { });
        },

        // ═══ 笔记功能 ═══
        _loadNotes: function () {
            var self = this;
            fetch('/api/notes/' + this.sutraId)
                .then(function (r) { return r.json(); })
                .then(function (data) { self.notesList = data.notes || []; })
                .catch(function () { self.notesList = []; });
        },

        saveNote: function () {
            var content = this.noteContent.trim();
            if (!content) return;
            var self = this;
            var body = {
                quote: this.noteQuote || '',
                content: content,
                juan: parseInt(this.currentJuan) || 1
            };
            fetch('/api/notes/' + this.sutraId, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.ok) {
                        self.noteSaveStatus = '✅ 已记录';
                        self.noteContent = '';
                        self.noteQuote = '';
                        self._loadNotes();
                        setTimeout(function () { self.noteSaveStatus = ''; }, 2000);
                    } else {
                        self.noteSaveStatus = '❌ 保存失败';
                    }
                })
                .catch(function () { self.noteSaveStatus = '❌ 网络错误'; });
        },

        loadJuan: function () {
            var url = '/api/content/' + this.sutraId + '/' + this.currentJuan;
            htmx.ajax('GET', url, '#reader-content');
            this._scrollToTop();
            this._updateUrl();
            this._originalHTML = null;
        },

        prevJuan: function () {
            if (this.currentJuan > 1) {
                this.currentJuan = parseInt(this.currentJuan) - 1;
                this.loadJuan();
            }
        },

        nextJuan: function () {
            if (this.currentJuan < this.totalJuan) {
                this.currentJuan = parseInt(this.currentJuan) + 1;
                this.loadJuan();
            }
        },

        _scrollToTop: function () {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        },

        _updateUrl: function () {
            var url = new URL(window.location);
            url.searchParams.set('juan', this.currentJuan);
            history.replaceState(null, '', url);
        }
    };
}

/* ═══════════════════════════════════════════════════════════
 * 尾注弹窗 — IIFE（独立于 Alpine.js）
 * ═══════════════════════════════════════════════════════════ */
(function () {
    var popup = null;
    var hideTimer = null;

    function ensurePopup() {
        if (!popup) {
            popup = document.createElement('div');
            popup.className = 'note-popup';
            document.body.appendChild(popup);
        }
        return popup;
    }

    function showPopup(target, noteIdx, noteText) {
        var p = ensurePopup();
        clearTimeout(hideTimer);
        p.innerHTML = '<span class="popup-num">[' + noteIdx + ']</span> ' + noteText;
        p.classList.add('visible');
        var rect = target.getBoundingClientRect();
        var top = rect.top - p.offsetHeight - 8;
        var left = rect.left;
        if (top < 10) top = rect.bottom + 8;
        if (left + p.offsetWidth > window.innerWidth - 20) left = window.innerWidth - p.offsetWidth - 20;
        if (left < 10) left = 10;
        p.style.top = top + 'px';
        p.style.left = left + 'px';
    }

    function hidePopup() {
        hideTimer = setTimeout(function () {
            if (popup) popup.classList.remove('visible');
        }, 150);
    }

    function wrapNotedText(container) {
        container.querySelectorAll('span.noted[data-note-text]:not(.app-var)').forEach(function (span) {
            if (span.textContent.trim()) return;
            var noteText = span.getAttribute('data-note-text') || '';
            var m = noteText.match(/^(.+?)【大】/);
            if (!m) return;
            var objText = m[1];
            if (!objText) return;
            var prevNode = span.previousSibling;
            if (!prevNode || prevNode.nodeType !== 3) return;
            var fullText = prevNode.textContent;
            if (!fullText.endsWith(objText)) return;
            prevNode.textContent = fullText.slice(0, -objText.length);
            span.textContent = objText;
        });
    }

    function bindNoteEvents(container) {
        wrapNotedText(container);
        container.querySelectorAll('span.noted[data-note-idx]').forEach(function (el) {
            el.addEventListener('mouseenter', function () {
                showPopup(el, el.getAttribute('data-note-idx'), el.getAttribute('data-note-text') || '');
            });
            el.addEventListener('mouseleave', hidePopup);
            el.addEventListener('click', function () {
                var idx = el.getAttribute('data-note-idx');
                var noteEl = document.getElementById('note-' + idx);
                if (noteEl) {
                    noteEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    history.pushState(null, '', '#note-' + idx);
                }
            });
        });
        container.querySelectorAll('sup.note-ref a[data-note-idx]').forEach(function (a) {
            a.addEventListener('mouseenter', function () {
                showPopup(a, a.getAttribute('data-note-idx'), a.getAttribute('data-note-text') || '');
            });
            a.addEventListener('mouseleave', hidePopup);
        });
        container.querySelectorAll('.note-back').forEach(function (a) {
            a.addEventListener('click', function (e) {
                e.preventDefault();
                var refEl = document.querySelector(a.getAttribute('href'));
                if (refEl) {
                    refEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    history.pushState(null, '', a.getAttribute('href'));
                }
            });
        });
        container.querySelectorAll('sup.note-ref a[href^="#note-"]').forEach(function (a) {
            a.addEventListener('click', function (e) {
                e.preventDefault();
                var noteEl = document.querySelector(a.getAttribute('href'));
                if (noteEl) {
                    noteEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    history.pushState(null, '', a.getAttribute('href'));
                }
            });
        });
    }

    document.addEventListener('htmx:afterSettle', function (e) {
        if (e.detail.target && e.detail.target.id === 'reader-content') {
            bindNoteEvents(e.detail.target);
            // 竖排模式下，新内容加载后重置滚动到经文开头（最右侧）
            var layout = document.getElementById('reader-layout');
            if (layout && layout.classList.contains('writing-vertical')) {
                setTimeout(function () {
                    var juanBody = document.querySelector('.juan-body');
                    if (juanBody) juanBody.scrollLeft = 0;
                }, 100);
            }
        }
    });

    document.addEventListener('DOMContentLoaded', function () {
        var reader = document.getElementById('reader-content');
        if (reader) bindNoteEvents(reader);
    });
})();
