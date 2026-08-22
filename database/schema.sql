-- SQLite Schema for Meow OS
-- Replaces previous partial schema with comprehensive definitions.

PRAGMA foreign_keys = ON;

-- TASKS
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    priority TEXT NOT NULL DEFAULT 'medium',
    priority_score REAL DEFAULT 0.0,
    due_date TEXT,
    estimated_minutes INTEGER,
    actual_minutes INTEGER,
    category TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',
    project_id TEXT,
    goal_ids TEXT DEFAULT '[]',
    source_type TEXT,
    source_id TEXT,
    source_confidence REAL DEFAULT 1.0,
    provenance_chain TEXT DEFAULT '[]',
    authority_level TEXT DEFAULT 'automatic',
    snoozed_until TEXT,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);
CREATE INDEX IF NOT EXISTS idx_tasks_project_id ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_source_type ON tasks(source_type);

-- Auto-update triggers
CREATE TRIGGER IF NOT EXISTS trigger_update_timestamp_tasks AFTER UPDATE ON tasks
BEGIN UPDATE tasks SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id; END;

-- EVENTS
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    title TEXT NOT NULL,
    description TEXT,
    event_type TEXT DEFAULT 'general',
    status TEXT NOT NULL DEFAULT 'todo',
    start_at TEXT,
    end_at TEXT,
    location TEXT,
    is_all_day BOOLEAN DEFAULT 0,
    is_fixed BOOLEAN DEFAULT 0,
    source_type TEXT,
    source_ids TEXT DEFAULT '[]',
    dedup_hash TEXT DEFAULT '',
    related_task_ids TEXT DEFAULT '[]',
    calendar_entry_id TEXT,
    tags TEXT DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_events_start_at ON events(start_at);

-- OPPORTUNITIES
CREATE TABLE IF NOT EXISTS opportunities (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    title TEXT NOT NULL,
    description TEXT,
    source_url TEXT,
    source_name TEXT,
    discovered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deadline_at TEXT,
    status TEXT DEFAULT 'discovered',
    action_url TEXT,
    tags TEXT DEFAULT '[]',
    relevance_score REAL DEFAULT 0.0,
    career_score REAL DEFAULT 0.0,
    nvidia_score REAL DEFAULT 0.0,
    skill_scores TEXT DEFAULT '{}',
    learning_value REAL DEFAULT 0.0,
    portfolio_value REAL DEFAULT 0.0,
    networking_value REAL DEFAULT 0.0,
    time_requirement_hours REAL,
    difficulty TEXT,
    eligibility TEXT
);
CREATE INDEX IF NOT EXISTS idx_opportunities_status ON opportunities(status);

-- MEMORIES
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    category TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    context TEXT,
    source TEXT,
    confidence REAL DEFAULT 1.0,
    is_sensitive BOOLEAN DEFAULT 0,
    tags TEXT DEFAULT '[]',
    last_accessed_at TEXT,
    expires_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);

-- PROJECTS
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    name TEXT NOT NULL,
    objective TEXT,
    description TEXT,
    status TEXT DEFAULT 'planning',
    repository_url TEXT,
    deadline TEXT,
    last_activity_at TEXT,
    next_action TEXT,
    dependencies TEXT DEFAULT '[]',
    risks TEXT DEFAULT '[]',
    progress_pct REAL DEFAULT 0.0,
    demo_readiness TEXT DEFAULT 'not_ready',
    resume_value_score REAL DEFAULT 0.0,
    goal_id TEXT,
    tags TEXT DEFAULT '[]'
);

-- EMAILS
CREATE TABLE IF NOT EXISTS emails (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    gmail_id TEXT,
    subject TEXT,
    sender TEXT,
    recipients TEXT DEFAULT '[]',
    body_preview TEXT,
    received_at TEXT,
    labels TEXT DEFAULT '[]',
    is_processed BOOLEAN DEFAULT 0,
    category TEXT,
    importance TEXT DEFAULT 'medium',
    extracted_tasks TEXT DEFAULT '[]',
    extracted_events TEXT DEFAULT '[]',
    detected_deadline TEXT,
    career_relevance REAL DEFAULT 0.0,
    academic_relevance REAL DEFAULT 0.0
);
CREATE INDEX IF NOT EXISTS idx_emails_received_at ON emails(received_at);

-- COURSES
CREATE TABLE IF NOT EXISTS courses (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    priority TEXT DEFAULT 'standard',
    career_alignment TEXT,
    semester TEXT,
    instructor TEXT,
    status TEXT DEFAULT 'in_progress',
    grade TEXT
);

-- ASSIGNMENTS
CREATE TABLE IF NOT EXISTS assignments (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    course_id TEXT,
    title TEXT NOT NULL,
    description TEXT,
    due_date TEXT,
    estimated_hours REAL,
    status TEXT DEFAULT 'todo',
    submission_url TEXT,
    source_type TEXT DEFAULT 'google_classroom',
    source_id TEXT,
    work_plan_created BOOLEAN DEFAULT 0,
    FOREIGN KEY(course_id) REFERENCES courses(id)
);
CREATE INDEX IF NOT EXISTS idx_assignments_course_id ON assignments(course_id);

-- NOTIFICATIONS
CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    notification_type TEXT DEFAULT 'info',
    priority TEXT DEFAULT 'medium',
    is_read BOOLEAN DEFAULT 0,
    is_dismissed BOOLEAN DEFAULT 0,
    action_url TEXT,
    action_label TEXT,
    related_entity_id TEXT,
    related_entity_type TEXT,
    expires_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_notifications_is_read ON notifications(is_read);

-- PERSONS
CREATE TABLE IF NOT EXISTS persons (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    name TEXT NOT NULL,
    email TEXT,
    role TEXT,
    organization TEXT,
    relationship TEXT,
    last_contact TEXT,
    notes TEXT
);

-- MEETINGS
CREATE TABLE IF NOT EXISTS meetings (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    title TEXT NOT NULL,
    event_id TEXT,
    organizer TEXT,
    participants TEXT DEFAULT '[]',
    agenda TEXT,
    notes TEXT,
    action_items TEXT DEFAULT '[]',
    meeting_date TEXT,
    FOREIGN KEY(event_id) REFERENCES events(id)
);
CREATE INDEX IF NOT EXISTS idx_meetings_event_id ON meetings(event_id);

-- AUDIT ENTRIES
CREATE TABLE IF NOT EXISTS audit_entries (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    agent_name TEXT NOT NULL,
    trigger TEXT NOT NULL,
    action TEXT NOT NULL,
    reason TEXT NOT NULL,
    source TEXT,
    result TEXT,
    confidence REAL DEFAULT 1.0,
    user_approved BOOLEAN,
    metadata TEXT DEFAULT '{}'
);

-- KNOWLEDGE GRAPH
CREATE TABLE IF NOT EXISTS kg_entities (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    entity_type TEXT NOT NULL,
    name TEXT NOT NULL,
    properties TEXT DEFAULT '{}',
    embedding_id TEXT
);
CREATE TABLE IF NOT EXISTS kg_relations (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    properties TEXT DEFAULT '{}',
    FOREIGN KEY(source_id) REFERENCES kg_entities(id),
    FOREIGN KEY(target_id) REFERENCES kg_entities(id)
);
CREATE INDEX IF NOT EXISTS idx_kg_relations_source ON kg_relations(source_id);
CREATE INDEX IF NOT EXISTS idx_kg_relations_target ON kg_relations(target_id);

-- SYNC STATE
CREATE TABLE IF NOT EXISTS sync_state (
    id TEXT PRIMARY KEY,
    connector_id TEXT NOT NULL,
    last_synced_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sync_token TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sync_state_connector_id ON sync_state(connector_id);

-- FTS5 TABLES (standalone — synced manually via triggers or application code)
CREATE VIRTUAL TABLE IF NOT EXISTS tasks_fts USING fts5(id UNINDEXED, title, description);
CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(id UNINDEXED, title, description, location);
CREATE VIRTUAL TABLE IF NOT EXISTS opportunities_fts USING fts5(id UNINDEXED, title, description, source_name);
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(id UNINDEXED, key, value, context);
CREATE VIRTUAL TABLE IF NOT EXISTS emails_fts USING fts5(id UNINDEXED, subject, sender, body_preview);

-- MIGRATIONS TABLE
CREATE TABLE IF NOT EXISTS migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

