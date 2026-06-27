-- Enable UUID extension if not enabled (useful if using older Postgres versions, default is enabled in Supabase)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Table 1: raw_profile_data
CREATE TABLE IF NOT EXISTS raw_profile_data (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source text NOT NULL, -- 'github' | 'stackoverflow' | 'devto' | 'hackernews'
  source_user_id text NOT NULL, -- the platform's own identifier for this user
  username text, -- handle used to fetch this data
  raw_data jsonb NOT NULL, -- the full raw dict returned by the ingestion client
  fetched_at timestamptz NOT NULL DEFAULT now(),
  ingestion_run_id uuid -- groups all fetches from one /resolve call together
);

-- Table 2: canonical_profiles
CREATE TABLE IF NOT EXISTS canonical_profiles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  display_name text,
  location text,
  bio text,
  primary_email text,
  merged_languages jsonb, -- {"Python": 45000, "TypeScript": 12000}
  merged_tags jsonb, -- {"python": 8, "fastapi": 3}
  resolution_confidence float, -- 0.0 to 1.0, overall confidence of the merge
  resolution_status text, -- 'resolved' | 'ambiguous' | 'unresolved'
  llm_summary text, -- paragraph from Gemini
  llm_tokens_used int,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- Table 3: profile_sources
CREATE TABLE IF NOT EXISTS profile_sources (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  canonical_profile_id uuid NOT NULL REFERENCES canonical_profiles(id) ON DELETE CASCADE,
  raw_profile_id uuid NOT NULL REFERENCES raw_profile_data(id) ON DELETE CASCADE,
  source text NOT NULL,
  confidence_score float NOT NULL, -- 0.0 to 1.0 for this specific link
  signals_fired jsonb, -- list of signal names that fired
  resolution_method text, -- 'rule_based' | 'llm_assisted'
  linked_at timestamptz NOT NULL DEFAULT now()
);

-- Table 4: resolution_requests
CREATE TABLE IF NOT EXISTS resolution_requests (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  input_query jsonb NOT NULL, -- the raw search input
  canonical_profile_id uuid REFERENCES canonical_profiles(id) ON DELETE SET NULL,
  status text NOT NULL, -- 'pending' | 'complete' | 'failed'
  error_message text,
  resolution_time_ms int,
  api_calls_made jsonb, -- {"github": 4, "stackoverflow": 2, ...}
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz
);

-- Table 5: observability_metrics
CREATE TABLE IF NOT EXISTS observability_metrics (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source text NOT NULL,
  endpoint text NOT NULL,
  status_code int,
  latency_ms int,
  tokens_used int, -- only for LLM calls
  called_at timestamptz NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_raw_profile_data_source_user_id ON raw_profile_data(source, source_user_id);
CREATE INDEX IF NOT EXISTS idx_raw_profile_data_ingestion_run_id ON raw_profile_data(ingestion_run_id);
CREATE INDEX IF NOT EXISTS idx_profile_sources_canonical_profile_id ON profile_sources(canonical_profile_id);
CREATE INDEX IF NOT EXISTS idx_resolution_requests_status ON resolution_requests(status);

-- Trigger function for updated_at on canonical_profiles
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger on canonical_profiles
DROP TRIGGER IF EXISTS trigger_canonical_profiles_updated_at ON canonical_profiles;
CREATE TRIGGER trigger_canonical_profiles_updated_at
BEFORE UPDATE ON canonical_profiles
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();
