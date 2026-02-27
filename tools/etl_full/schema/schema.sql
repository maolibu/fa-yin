-- CBETA 佛经数据库 Schema
-- 用于法印对照 (Sutra-Lineage) 项目

-- 1. 经典目录（从 XML teiHeader 提取）
CREATE TABLE IF NOT EXISTS catalog (
    sutra_id   TEXT PRIMARY KEY,  -- 如 'T0251'
    canon      TEXT NOT NULL,     -- 如 'T'（大正藏）
    volume     TEXT,              -- 如 '08'
    title      TEXT,              -- 如 '般若波羅蜜多心經'
    author     TEXT,              -- 如 '唐 玄奘譯'
    total_juan INTEGER DEFAULT 1, -- 卷数
    category   TEXT               -- 藏经中文名（如 '大正新脩大藏經'）
);

-- 2. 经文内容（按卷存储）
CREATE TABLE IF NOT EXISTS content (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    sutra_id   TEXT NOT NULL,     -- 外键 → catalog
    juan       INTEGER NOT NULL,  -- 卷号
    html       TEXT,              -- 用于显示的 HTML（保留行号标记）
    plain_text TEXT,              -- 去标签纯文本（用于 FTS 搜索）
    FOREIGN KEY (sutra_id) REFERENCES catalog(sutra_id),
    UNIQUE(sutra_id, juan)        -- 同一经的同一卷不重复
);

-- 3. 全文检索索引（FTS5 + Trigram 分词）
CREATE VIRTUAL TABLE IF NOT EXISTS content_fts USING fts5(
    sutra_id,
    juan,
    plain_text,
    content=content,
    content_rowid=id,
    tokenize='trigram'
);

-- FTS 同步触发器：content 插入/删除时自动更新 FTS 索引
CREATE TRIGGER IF NOT EXISTS content_ai AFTER INSERT ON content BEGIN
    INSERT INTO content_fts(rowid, sutra_id, juan, plain_text)
    VALUES (new.id, new.sutra_id, new.juan, new.plain_text);
END;

CREATE TRIGGER IF NOT EXISTS content_ad AFTER DELETE ON content BEGIN
    INSERT INTO content_fts(content_fts, rowid, sutra_id, juan, plain_text)
    VALUES ('delete', old.id, old.sutra_id, old.juan, old.plain_text);
END;

CREATE TRIGGER IF NOT EXISTS content_au AFTER UPDATE ON content BEGIN
    INSERT INTO content_fts(content_fts, rowid, sutra_id, juan, plain_text)
    VALUES ('delete', old.id, old.sutra_id, old.juan, old.plain_text);
    INSERT INTO content_fts(rowid, sutra_id, juan, plain_text)
    VALUES (new.id, new.sutra_id, new.juan, new.plain_text);
END;

-- 4. 校勘记（<app>/<lem>/<rdg> 异读）
CREATE TABLE IF NOT EXISTS apparatus (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    sutra_id   TEXT NOT NULL,
    juan       INTEGER NOT NULL,
    line_id    TEXT,              -- 最近的行号 (lb n=xxx)
    lem_text   TEXT,              -- 底本正文
    readings   TEXT,              -- JSON: [{"wit":"宋","text":"..."},...]
    FOREIGN KEY (sutra_id) REFERENCES catalog(sutra_id)
);

-- 5. 注释（<note> 内容）
CREATE TABLE IF NOT EXISTS notes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    sutra_id   TEXT NOT NULL,
    juan       INTEGER NOT NULL,
    line_id    TEXT,              -- 最近的行号
    note_type  TEXT,              -- note 的 type 属性
    place      TEXT,              -- inline/foot 等
    content    TEXT,
    FOREIGN KEY (sutra_id) REFERENCES catalog(sutra_id)
);

-- 6. 目录结构（<cb:mulu> 品/分/卷标题）
CREATE TABLE IF NOT EXISTS toc (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    sutra_id   TEXT NOT NULL,
    juan       INTEGER,
    level      INTEGER DEFAULT 0, -- 目录层级
    type       TEXT,              -- 卷/品/分 等
    n          TEXT,              -- mulu 的 n 属性
    title      TEXT,
    FOREIGN KEY (sutra_id) REFERENCES catalog(sutra_id)
);

-- 索引：加速查询
CREATE INDEX IF NOT EXISTS idx_catalog_canon ON catalog(canon);
CREATE INDEX IF NOT EXISTS idx_content_sutra ON content(sutra_id);
CREATE INDEX IF NOT EXISTS idx_apparatus_sutra ON apparatus(sutra_id);
CREATE INDEX IF NOT EXISTS idx_notes_sutra ON notes(sutra_id);
CREATE INDEX IF NOT EXISTS idx_toc_sutra ON toc(sutra_id);
