-- Accounts remain a browser mock. These identifiers are authenticated subjects,
-- so replacing the account service does not change planning ownership.
CREATE TABLE IF NOT EXISTS studio_source_assignments (
  source_id uuid NOT NULL REFERENCES studio_sources(id),
  account_id text NOT NULL CHECK (length(account_id) BETWEEN 1 AND 100),
  assigned_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (source_id, account_id)
);
CREATE INDEX IF NOT EXISTS studio_source_assignments_account ON studio_source_assignments(account_id);

-- A plan can now belong to an assignee, while its immutable source still belongs
-- to the person who prepared it. Preserve the snapshot/source pair constraint.
ALTER TABLE studio_projects DROP CONSTRAINT IF EXISTS studio_projects_source_id_owner_id_fkey;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='studio_projects_assigned_source_fkey') THEN
    ALTER TABLE studio_projects ADD CONSTRAINT studio_projects_assigned_source_fkey
      FOREIGN KEY (source_id) REFERENCES studio_sources(id);
  END IF;
END $$;
