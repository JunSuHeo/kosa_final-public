CREATE TABLE IF NOT EXISTS studio_projects (
  id uuid PRIMARY KEY, owner_id text NOT NULL, title text NOT NULL, idea text NOT NULL,
  current_version integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS studio_owner ON studio_projects(owner_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS studio_revisions (
  project_id uuid REFERENCES studio_projects(id), version integer NOT NULL,
  snapshot jsonb NOT NULL, summary text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(project_id, version)
);
CREATE OR REPLACE FUNCTION studio_immutable_revision() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Approved revisions are immutable'; END; $$;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='studio_revision_immutable') THEN
    CREATE TRIGGER studio_revision_immutable BEFORE UPDATE OR DELETE ON studio_revisions
    FOR EACH ROW EXECUTE FUNCTION studio_immutable_revision();
  END IF;
END $$;
CREATE TABLE IF NOT EXISTS studio_jobs (
  id uuid PRIMARY KEY, project_id uuid NOT NULL REFERENCES studio_projects(id),
  base_version integer NOT NULL, kind text NOT NULL CHECK(kind IN ('generate','revise')),
  status text NOT NULL CHECK(status IN ('queued','running','awaiting_answers','waiting_review','completed','failed','cancelled')),
  stage text NOT NULL DEFAULT 'questions', request text NOT NULL,
  questions jsonb NOT NULL DEFAULT '[]', answers jsonb NOT NULL DEFAULT '{}',
  partial jsonb NOT NULL DEFAULT '{}', provider text NOT NULL, model text NOT NULL, ai_mode text NOT NULL,
  error text, usage jsonb NOT NULL DEFAULT '[]',
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS studio_one_active_job ON studio_jobs(project_id)
WHERE status IN ('queued','running','awaiting_answers','waiting_review');
CREATE TABLE IF NOT EXISTS studio_proposals (
  id uuid PRIMARY KEY, project_id uuid NOT NULL REFERENCES studio_projects(id),
  job_id uuid UNIQUE REFERENCES studio_jobs(id), base_version integer NOT NULL,
  candidate jsonb NOT NULL, summary text NOT NULL, issues jsonb NOT NULL, diff jsonb NOT NULL,
  status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected','superseded')),
  approved_version integer, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS studio_one_pending ON studio_proposals(project_id) WHERE status='pending';
CREATE TABLE IF NOT EXISTS studio_messages (
  id bigserial PRIMARY KEY, project_id uuid NOT NULL REFERENCES studio_projects(id),
  role text NOT NULL CHECK(role IN ('user','assistant')), content text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
