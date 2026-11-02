-- 可选：PostgreSQL 记录表（不设 PGHOST 时程序用内存，无需建表）
CREATE SCHEMA IF NOT EXISTS amazon_agent;
CREATE TABLE IF NOT EXISTS amazon_agent.generations (
  id bigserial PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now(),
  asin varchar(16) NOT NULL,
  mode varchar(8) NOT NULL CHECK (mode IN ('model','demo')),
  model varchar(64), model_used varchar(64), fallback_chain jsonb,
  validation_ok boolean NOT NULL, validation_passed int NOT NULL, validation_failed int NOT NULL,
  validation jsonb NOT NULL, retries smallint NOT NULL,
  fallback_reason varchar(80), forced_fail boolean NOT NULL DEFAULT false,
  result jsonb NOT NULL,
  client_ip inet, duration_ms int, tokens_in int, tokens_out int,
  model_choice text, data_source text, product jsonb,
  image_requested boolean NOT NULL DEFAULT false, image_count int NOT NULL DEFAULT 0,
  image_ok boolean, images jsonb NOT NULL DEFAULT '[]', quota_counted boolean NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS generations_created_at ON amazon_agent.generations (created_at);
CREATE TABLE IF NOT EXISTS amazon_agent.reviews (
  id bigserial PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now(),
  generation_id bigint NOT NULL REFERENCES amazon_agent.generations(id),
  asin varchar(16) NOT NULL,
  result_snapshot jsonb NOT NULL,
  client_ip inet,
  status varchar(16) NOT NULL DEFAULT 'pending'
);
CREATE TABLE IF NOT EXISTS amazon_agent.daily_quota (
  day date NOT NULL, kind text NOT NULL, used int NOT NULL DEFAULT 0,
  PRIMARY KEY (day, kind)
);
