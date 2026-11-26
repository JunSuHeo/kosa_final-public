CREATE TABLE studio_github_connections (
  owner_id text PRIMARY KEY,
  login text NOT NULL,
  credentials bytea NOT NULL,
  expires_at timestamptz NOT NULL
);

CREATE TABLE studio_github_authorizations (
  owner_id text PRIMARY KEY,
  state_hash text NOT NULL,
  verifier text NOT NULL,
  expires_at timestamptz NOT NULL,
  claimed boolean NOT NULL DEFAULT false
);

ALTER TABLE studio_github_connections ENABLE ROW LEVEL SECURITY;
ALTER TABLE studio_github_authorizations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON studio_github_connections, studio_github_authorizations FROM PUBLIC;
DO $$ BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname='anon') THEN
    REVOKE ALL ON studio_github_connections, studio_github_authorizations FROM anon;
  END IF;
  IF EXISTS (SELECT FROM pg_roles WHERE rolname='authenticated') THEN
    REVOKE ALL ON studio_github_connections, studio_github_authorizations FROM authenticated;
  END IF;
END $$;
GRANT SELECT, INSERT, UPDATE ON studio_github_connections TO studio_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON studio_github_authorizations TO studio_runtime;
CREATE POLICY studio_server ON studio_github_connections TO studio_runtime USING (true) WITH CHECK (true);
CREATE POLICY studio_server ON studio_github_authorizations TO studio_runtime USING (true) WITH CHECK (true);
