CREATE TABLE IF NOT EXISTS studio_reviews (
  id uuid PRIMARY KEY, project_id uuid NOT NULL REFERENCES studio_projects(id),
  target_key text NOT NULL, proposal_id uuid REFERENCES studio_proposals(id), version integer NOT NULL,
  snapshot jsonb NOT NULL, snapshot_hash text NOT NULL,
  status text NOT NULL CHECK(status IN ('queued','running','completed','partial','failed')),
  provider text NOT NULL, model text NOT NULL, ai_mode text NOT NULL, prompt_version text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(project_id,target_key)
);
CREATE TABLE IF NOT EXISTS studio_review_agents (
  review_id uuid NOT NULL REFERENCES studio_reviews(id),
  role text NOT NULL CHECK(role IN ('developer','planner','security','ux','qa')),
  status text NOT NULL CHECK(status IN ('queued','running','completed','failed')),
  result jsonb, error text, usage jsonb, updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(review_id,role)
);
