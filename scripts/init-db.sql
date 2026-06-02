-- PostgreSQL schema initialization for the image processing service.
-- This is run automatically by the application on first startup.

CREATE TABLE IF NOT EXISTS images (
    id UUID PRIMARY KEY,
    user_id BIGINT NOT NULL,
    original_s3_key TEXT NOT NULL,
    processed_s3_key TEXT,
    status TEXT NOT NULL DEFAULT 'received',
    error_reason TEXT,
    telegram_message_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    final_status_sent_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_images_user_id ON images (user_id);
CREATE INDEX IF NOT EXISTS idx_images_status ON images (status);
CREATE INDEX IF NOT EXISTS idx_images_user_status ON images (user_id, status);
