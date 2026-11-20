ALTER TABLE studio_jobs DROP CONSTRAINT IF EXISTS studio_jobs_kind_check;
ALTER TABLE studio_jobs ADD CONSTRAINT studio_jobs_kind_check
  CHECK (kind IN ('generate','revise','discuss','repair'));
ALTER TABLE studio_jobs ADD COLUMN IF NOT EXISTS prompt_version text NOT NULL DEFAULT 'studio.v1';
ALTER TABLE studio_jobs ADD COLUMN IF NOT EXISTS base_proposal_id uuid REFERENCES studio_proposals(id);
ALTER TABLE studio_projects ADD COLUMN IF NOT EXISTS start_mode text NOT NULL DEFAULT 'generate';
ALTER TABLE studio_projects ADD COLUMN IF NOT EXISTS planning_intent text NOT NULL DEFAULT 'improve';
ALTER TABLE studio_projects ADD COLUMN IF NOT EXISTS conversation_brief jsonb;
ALTER TABLE studio_sources ADD COLUMN IF NOT EXISTS last_checked_at timestamptz;

CREATE TABLE IF NOT EXISTS studio_source_publications (
  id uuid PRIMARY KEY, source_id uuid NOT NULL REFERENCES studio_sources(id),
  snapshot_id uuid NOT NULL REFERENCES studio_code_snapshots(id), owner_id text NOT NULL,
  consent jsonb, scope jsonb NOT NULL, design_profile jsonb NOT NULL,
  fingerprint text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(source_id,fingerprint)
);
CREATE OR REPLACE FUNCTION studio_immutable_publication() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Published source scopes are immutable'; END; $$;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='studio_publication_immutable') THEN
    CREATE TRIGGER studio_publication_immutable BEFORE UPDATE OR DELETE ON studio_source_publications
    FOR EACH ROW EXECUTE FUNCTION studio_immutable_publication();
  END IF;
END $$;
ALTER TABLE studio_sources ADD COLUMN IF NOT EXISTS publication_id uuid REFERENCES studio_source_publications(id);
ALTER TABLE studio_projects ADD COLUMN IF NOT EXISTS source_publication_id uuid REFERENCES studio_source_publications(id);
CREATE OR REPLACE FUNCTION studio_project_source_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (OLD.planning_type,OLD.source_id,OLD.code_snapshot_id,OLD.forked_from,OLD.code_model_consent,OLD.source_publication_id,OLD.start_mode,OLD.planning_intent)
      IS DISTINCT FROM
     (NEW.planning_type,NEW.source_id,NEW.code_snapshot_id,NEW.forked_from,NEW.code_model_consent,NEW.source_publication_id,NEW.start_mode,NEW.planning_intent)
  THEN RAISE EXCEPTION 'Planning source is immutable'; END IF;
  RETURN NEW;
END $$;
