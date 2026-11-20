-- API/worker logins inherit this role; the migration owner remains separate.
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='studio_runtime') THEN
    CREATE ROLE studio_runtime NOLOGIN;
  END IF;
END $$;
GRANT USAGE ON SCHEMA public TO studio_runtime;
DO $$
DECLARE t record; constraint_row record; sequence_row record;
BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname='public' AND left(tablename,7)='studio_' LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',t.tablename);
    EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC',t.tablename);
    IF EXISTS (SELECT FROM pg_roles WHERE rolname='anon') THEN
      EXECUTE format('REVOKE ALL ON public.%I FROM anon',t.tablename);
    END IF;
    IF EXISTS (SELECT FROM pg_roles WHERE rolname='authenticated') THEN
      EXECUTE format('REVOKE ALL ON public.%I FROM authenticated',t.tablename);
    END IF;
    EXECUTE format('DROP POLICY IF EXISTS studio_server ON public.%I',t.tablename);
    EXECUTE format('CREATE POLICY studio_server ON public.%I TO studio_runtime USING (true) WITH CHECK (true)',t.tablename);
    IF t.tablename = 'studio_schema_migrations' THEN
      EXECUTE format('GRANT SELECT ON public.%I TO studio_runtime',t.tablename);
    ELSIF t.tablename IN ('studio_audit','studio_data_transfers') THEN
      EXECUTE format('GRANT SELECT,INSERT ON public.%I TO studio_runtime',t.tablename);
    ELSE
      EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON public.%I TO studio_runtime',t.tablename);
    END IF;
  END LOOP;
  FOR sequence_row IN SELECT sequencename FROM pg_sequences WHERE schemaname='public' AND left(sequencename,7)='studio_' LOOP
    EXECUTE format('GRANT USAGE,SELECT ON SEQUENCE public.%I TO studio_runtime',sequence_row.sequencename);
  END LOOP;
  -- Data transfer inserts all rows without disabling immutable guards. Deferred FKs
  -- allow the existing source/publication and project/fork reference cycles.
  FOR constraint_row IN
    SELECT conrelid::regclass AS relation,conname FROM pg_constraint
    WHERE contype='f' AND connamespace='public'::regnamespace
      AND left(conrelid::regclass::text,7)='studio_'
  LOOP
    EXECUTE format('ALTER TABLE %s ALTER CONSTRAINT %I DEFERRABLE INITIALLY IMMEDIATE',constraint_row.relation,constraint_row.conname);
  END LOOP;
END $$;
