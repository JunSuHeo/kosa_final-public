CREATE TABLE IF NOT EXISTS studio_sources (
  id uuid PRIMARY KEY, owner_id text NOT NULL, name text NOT NULL, description text NOT NULL,
  kind text NOT NULL CHECK (kind IN ('local','github')), repository text NOT NULL, ref text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id,owner_id), UNIQUE (owner_id,kind,repository,ref)
);
CREATE TABLE IF NOT EXISTS studio_code_snapshots (
  id uuid PRIMARY KEY, source_id uuid NOT NULL REFERENCES studio_sources(id), commit_sha text NOT NULL,
  analysis_version text NOT NULL, dirty boolean NOT NULL DEFAULT false,
  status text NOT NULL CHECK (status IN ('queued','running','ready','failed')),
  analysis jsonb, error text, created_at timestamptz NOT NULL DEFAULT now(),
  CHECK ((status='ready') = (analysis IS NOT NULL)),
  UNIQUE (id,source_id), UNIQUE (source_id,commit_sha,analysis_version)
);
CREATE OR REPLACE FUNCTION studio_code_snapshot_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Code snapshots are retained'; END IF;
  IF OLD.status='ready' OR
     (OLD.id,OLD.source_id,OLD.commit_sha,OLD.analysis_version,OLD.dirty,OLD.created_at)
       IS DISTINCT FROM
     (NEW.id,NEW.source_id,NEW.commit_sha,NEW.analysis_version,NEW.dirty,NEW.created_at)
  THEN RAISE EXCEPTION 'Code snapshot basis is immutable'; END IF;
  RETURN NEW;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='studio_code_snapshot_guard_trigger') THEN
    CREATE TRIGGER studio_code_snapshot_guard_trigger BEFORE UPDATE OR DELETE ON studio_code_snapshots
    FOR EACH ROW EXECUTE FUNCTION studio_code_snapshot_guard();
  END IF;
END $$;

ALTER TABLE studio_projects
  ADD COLUMN IF NOT EXISTS planning_type text NOT NULL DEFAULT 'new',
  ADD COLUMN IF NOT EXISTS source_id uuid,
  ADD COLUMN IF NOT EXISTS code_snapshot_id uuid,
  ADD COLUMN IF NOT EXISTS forked_from uuid REFERENCES studio_projects(id),
  ADD COLUMN IF NOT EXISTS code_model_consent jsonb;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='studio_project_source_pair') THEN
    ALTER TABLE studio_projects
      ADD CONSTRAINT studio_project_source_pair CHECK (
        (planning_type='new' AND source_id IS NULL AND code_snapshot_id IS NULL
          AND forked_from IS NULL AND code_model_consent IS NULL)
        OR (planning_type='existing' AND source_id IS NOT NULL AND code_snapshot_id IS NOT NULL)),
      ADD FOREIGN KEY (source_id,owner_id) REFERENCES studio_sources(id,owner_id),
      ADD FOREIGN KEY (code_snapshot_id,source_id) REFERENCES studio_code_snapshots(id,source_id);
  END IF;
END $$;
CREATE OR REPLACE FUNCTION studio_project_source_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (OLD.planning_type,OLD.source_id,OLD.code_snapshot_id,OLD.forked_from,OLD.code_model_consent)
      IS DISTINCT FROM
     (NEW.planning_type,NEW.source_id,NEW.code_snapshot_id,NEW.forked_from,NEW.code_model_consent)
  THEN RAISE EXCEPTION 'Planning source is immutable'; END IF;
  RETURN NEW;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='studio_project_source_guard_trigger') THEN
    CREATE TRIGGER studio_project_source_guard_trigger BEFORE UPDATE ON studio_projects
    FOR EACH ROW EXECUTE FUNCTION studio_project_source_guard();
  END IF;
END $$;
ALTER TABLE studio_jobs ADD COLUMN IF NOT EXISTS code_snapshot_id uuid REFERENCES studio_code_snapshots(id);
ALTER TABLE studio_reviews ADD COLUMN IF NOT EXISTS code_snapshot_id uuid REFERENCES studio_code_snapshots(id);
ALTER TABLE studio_review_agents ADD COLUMN IF NOT EXISTS attempts jsonb NOT NULL DEFAULT '[]';
ALTER TABLE studio_sources
  ADD COLUMN IF NOT EXISTS current_snapshot_id uuid REFERENCES studio_code_snapshots(id),
  ADD COLUMN IF NOT EXISTS last_error text,
  ADD COLUMN IF NOT EXISTS working_tree_dirty boolean NOT NULL DEFAULT false;
ALTER TABLE studio_sources ADD COLUMN IF NOT EXISTS analysis_paths text[] NOT NULL DEFAULT '{}';
