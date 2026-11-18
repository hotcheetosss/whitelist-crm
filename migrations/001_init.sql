-- All timestamps are TEXT in the single format YYYY-MM-DDTHH:MM:SSZ (UTC).
-- One fixed format makes string comparison equal to chronological comparison,
-- which the overlap checks in SQL rely on.

CREATE TABLE managers (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL CHECK (length(trim(name)) > 0),
    created_at TEXT NOT NULL
);

CREATE TABLE companies (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL CHECK (length(trim(name)) > 0),
    bin        TEXT NOT NULL UNIQUE CHECK (length(bin) = 12 AND bin NOT GLOB '*[^0-9]*'),
    phone      TEXT,
    -- Result of the latest call; 'new' while there were no calls.
    status     TEXT NOT NULL DEFAULT 'new'
               CHECK (status IN ('new', 'no_answer', 'refused', 'meeting_set')),
    created_at TEXT NOT NULL
);

CREATE TABLE meetings (
    id                 INTEGER PRIMARY KEY,
    company_id         INTEGER NOT NULL REFERENCES companies (id),
    manager_id         INTEGER NOT NULL REFERENCES managers (id),
    starts_at          TEXT NOT NULL,
    ends_at            TEXT NOT NULL,
    -- Set on creation and never updated: shows when the meeting was first planned for.
    original_starts_at TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'scheduled'
                       CHECK (status IN ('scheduled', 'cancelled')),
    created_at         TEXT NOT NULL,
    CHECK (starts_at < ends_at)
);

CREATE INDEX idx_meetings_manager_time ON meetings (manager_id, starts_at);
CREATE INDEX idx_meetings_company_status ON meetings (company_id, status);

-- Append-only history: one row per action on a meeting.
CREATE TABLE meeting_events (
    id            INTEGER PRIMARY KEY,
    meeting_id    INTEGER NOT NULL REFERENCES meetings (id),
    action        TEXT NOT NULL CHECK (action IN ('created', 'rescheduled', 'cancelled')),
    old_starts_at TEXT,
    new_starts_at TEXT,
    created_at    TEXT NOT NULL
);

CREATE INDEX idx_meeting_events_meeting ON meeting_events (meeting_id, id);

CREATE TRIGGER meeting_events_no_update BEFORE UPDATE ON meeting_events
BEGIN
    SELECT RAISE(ABORT, 'meeting_events is append-only');
END;

CREATE TRIGGER meeting_events_no_delete BEFORE DELETE ON meeting_events
BEGIN
    SELECT RAISE(ABORT, 'meeting_events is append-only');
END;

CREATE TABLE calls (
    id         INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies (id),
    result     TEXT NOT NULL CHECK (result IN ('no_answer', 'refused', 'meeting_set')),
    meeting_id INTEGER REFERENCES meetings (id),
    comment    TEXT,
    called_at  TEXT NOT NULL,
    -- A meeting is referenced if and only if the result is meeting_set.
    CHECK ((result = 'meeting_set') = (meeting_id IS NOT NULL))
);

CREATE INDEX idx_calls_company ON calls (company_id, called_at);
