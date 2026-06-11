CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY,
    params JSONB NOT NULL,
    result JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS building_codes (
    id SERIAL PRIMARY KEY,
    country VARCHAR(10) NOT NULL,
    code_name VARCHAR(100) NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding vector(768),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS building_codes_embedding_idx
    ON building_codes USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
