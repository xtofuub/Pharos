-- Pharos 0.3.2: distinguish scan warnings and failed files from completed work.
ALTER TABLE index_jobs ADD COLUMN files_failed INTEGER NOT NULL DEFAULT 0;
ALTER TABLE index_jobs ADD COLUMN warnings_count INTEGER NOT NULL DEFAULT 0;
