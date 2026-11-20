CREATE TABLE IF NOT EXISTS studio_accounts (
  id text PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 100),
  auth_user_id uuid NOT NULL UNIQUE,
  login_id text NOT NULL UNIQUE CHECK (login_id ~ '^[a-zA-Z0-9._-]{3,40}$'),
  name text NOT NULL CHECK (length(name) BETWEEN 1 AND 80),
  role text NOT NULL CHECK (role IN ('USER1','USER2','ADMINISTRATOR')),
  active boolean NOT NULL DEFAULT false,
  session_version integer NOT NULL DEFAULT 1 CHECK (session_version > 0),
  provisioning_status text NOT NULL DEFAULT 'pending' CHECK (provisioning_status IN ('pending','ready')),
  created_at timestamptz NOT NULL DEFAULT now(), last_login_at timestamptz
);
CREATE TABLE IF NOT EXISTS studio_role_permissions (
  role text NOT NULL CHECK (role IN ('USER1','USER2','ADMINISTRATOR')),
  permission text NOT NULL,
  enabled boolean NOT NULL,
  PRIMARY KEY(role,permission)
);
CREATE TABLE IF NOT EXISTS studio_auth_sessions (
  id uuid PRIMARY KEY,
  account_id text NOT NULL REFERENCES studio_accounts(id),
  session_version integer NOT NULL,
  revoked boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS studio_sessions_account ON studio_auth_sessions(account_id) WHERE NOT revoked;
CREATE TABLE IF NOT EXISTS studio_account_operations (
  id uuid PRIMARY KEY,
  actor_id text NOT NULL,
  account_id text NOT NULL REFERENCES studio_accounts(id),
  action text NOT NULL CHECK (action IN ('create','reset')),
  input jsonb NOT NULL,
  completed boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS studio_audit (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  at timestamptz NOT NULL DEFAULT now(),
  actor text NOT NULL, action text NOT NULL, target text NOT NULL, detail text NOT NULL
);
CREATE INDEX IF NOT EXISTS studio_audit_time ON studio_audit(at DESC,id DESC);
CREATE TABLE IF NOT EXISTS studio_login_attempts (
  key text PRIMARY KEY, started_at timestamptz NOT NULL DEFAULT now(), attempts integer NOT NULL
);
CREATE TABLE IF NOT EXISTS studio_data_transfers (
  id uuid PRIMARY KEY, manifest jsonb NOT NULL, completed_at timestamptz NOT NULL DEFAULT now()
);
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['studio_accounts','studio_role_permissions','studio_auth_sessions',
    'studio_account_operations','studio_audit','studio_login_attempts','studio_data_transfers'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
    EXECUTE format('REVOKE ALL ON %I FROM PUBLIC',t);
  END LOOP;
END $$;
