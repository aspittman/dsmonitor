-- The login/password are provisioned separately and never committed.
-- Only aggregate operational state is exposed; no row payloads or credentials.
CREATE OR REPLACE FUNCTION public.dsmonitor_overview()
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog
AS $$
 SELECT jsonb_build_object(
  'observed_at', now(),
  'database_bytes', pg_database_size(current_database()),
  'connections', (SELECT count(*) FROM pg_stat_activity WHERE datname=current_database()),
  'active_connections', (SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND state='active'),
  'workflow_counts', (SELECT coalesce(jsonb_object_agg(status,n),'{}'::jsonb) FROM (SELECT status,count(*) n FROM public.workflow_runs GROUP BY status) x),
  'execution_counts', (SELECT coalesce(jsonb_object_agg(status,n),'{}'::jsonb) FROM (SELECT status,count(*) n FROM public.execution_requests GROUP BY status) x)
 );
$$;
REVOKE ALL ON FUNCTION public.dsmonitor_overview() FROM PUBLIC, anon, authenticated;
GRANT USAGE ON SCHEMA public TO dsmonitor_usage_reader;
GRANT EXECUTE ON FUNCTION public.dsmonitor_overview() TO dsmonitor_usage_reader;
