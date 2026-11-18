-- The backend connects as the table owner. Other roles have no row policies.
ALTER TABLE studio_projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE studio_revisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE studio_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE studio_proposals ENABLE ROW LEVEL SECURITY;
ALTER TABLE studio_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE studio_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE studio_review_agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE studio_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE studio_code_snapshots ENABLE ROW LEVEL SECURITY;
