PRAGMA foreign_keys = ON;
PRAGMA journal_mode = DELETE;
PRAGMA synchronous = FULL;

CREATE TABLE dynasties (
    dynasty_id  INTEGER PRIMARY KEY,
    name_zh     TEXT NOT NULL,
    name_en     TEXT,
    type        TEXT
);

CREATE TABLE eras (
    era_id      INTEGER PRIMARY KEY,
    dynasty_id  INTEGER,
    emperor_id  INTEGER,
    name_zh     TEXT NOT NULL,
    name_en     TEXT,
    start_year  INTEGER,
    end_year    INTEGER,
    FOREIGN KEY (dynasty_id) REFERENCES dynasties(dynasty_id)
);

CREATE TABLE persons (
    person_id     TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    aliases       TEXT,
    birth_year    INTEGER,
    death_year    INTEGER,
    dynasty       TEXT,
    sect          TEXT,
    gender        INTEGER,
    is_monk       INTEGER DEFAULT 0,
    bio_concise   TEXT,
    bio_extensive TEXT,
    cbeta_refs    TEXT,
    works         TEXT,
    place_origin  TEXT
);

CREATE TABLE places (
    place_id    TEXT PRIMARY KEY,
    name_zh     TEXT NOT NULL,
    name_en     TEXT,
    name_ja     TEXT,
    latitude    REAL,
    longitude   REAL,
    district    TEXT,
    category    TEXT,
    note        TEXT,
    cbeta_refs  TEXT
);

CREATE TABLE edges (
    source_id   TEXT NOT NULL,
    target_id   TEXT NOT NULL,
    edge_type   TEXT NOT NULL DEFAULT 'teacher',
    description TEXT,
    cbeta_ref   TEXT,
    PRIMARY KEY (source_id, target_id)
);

CREATE TABLE person_scriptures (
    person_id    TEXT NOT NULL,
    scripture_id TEXT NOT NULL,
    relation     TEXT NOT NULL,
    source_text  TEXT,
    url          TEXT,
    PRIMARY KEY (person_id, scripture_id, relation)
);

CREATE INDEX idx_edges_source ON edges(source_id);
CREATE INDEX idx_edges_target ON edges(target_id);
CREATE INDEX idx_edges_type ON edges(edge_type);
CREATE INDEX idx_eras_dynasty ON eras(dynasty_id);
CREATE INDEX idx_persons_dynasty ON persons(dynasty);
CREATE INDEX idx_persons_sect ON persons(sect);
CREATE INDEX idx_places_category ON places(category);
CREATE INDEX idx_ps_person ON person_scriptures(person_id);
CREATE INDEX idx_ps_scripture ON person_scriptures(scripture_id);
