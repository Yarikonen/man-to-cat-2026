-- PostgreSQL schema for man-to-cat data pipeline
-- Table: processed_images
-- Purpose: Tracks image processing state across segmentation and preprocessing stages
-- Research pattern: STATE-01/02 from 01-RESEARCH.md

CREATE TABLE IF NOT EXISTS processed_images (
    id SERIAL PRIMARY KEY,
    s3_bucket VARCHAR(255) NOT NULL,
    s3_key VARCHAR(1024) NOT NULL,

    -- Processing flags
    processed BOOLEAN DEFAULT FALSE,

    -- Stage-specific status tracking
    segmentation_status VARCHAR(50),  -- pending, processing, success, failed, skipped
    preprocessing_status VARCHAR(50),  -- pending, processing, success, failed, skipped

    -- Error tracking
    error_message TEXT,
    attempt_count INTEGER DEFAULT 0,

    -- Timestamps for pipeline tracking
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processing_started_at TIMESTAMP WITH TIME ZONE,
    processing_completed_at TIMESTAMP WITH TIME ZONE,

    -- Additional metadata (JSON for flexibility)
    image_metadata JSONB,
    segmentation_metadata JSONB,  -- bbox coordinates, masks, labels
    preprocessing_metadata JSONB,  -- augmentations applied, format changes

    -- Idempotency: Prevent duplicate processing
    UNIQUE (s3_bucket, s3_key)
);

-- Indexes for query performance
-- Index for s3 location lookups (fast idempotency checks)
CREATE INDEX IF NOT EXISTS idx_s3_location ON processed_images (s3_bucket, s3_key);

-- Index for status-based queries (Airflow polling)
CREATE INDEX IF NOT EXISTS idx_processing_status ON processed_images (segmentation_status, preprocessing_status);

-- Index for monitoring queue delay (processing_started_at - created_at)
CREATE INDEX IF NOT EXISTS idx_created_at ON processed_images (created_at);

-- Index for retrieving unprocessed images (failed retry logic)
CREATE INDEX IF NOT EXISTS idx_unprocessed ON processed_images (s3_bucket, s3_key)
WHERE processed = FALSE;

-- Index for failed images needing retry
CREATE INDEX IF NOT EXISTS idx_failed_images ON processed_images (segmentation_status, preprocessing_status)
WHERE segmentation_status = 'failed' OR preprocessing_status = 'failed';

-- Function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger to automatically update updated_at on row changes
CREATE TRIGGER update_processed_images_updated_at
    BEFORE UPDATE ON processed_images
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- View for monitoring pipeline metrics
CREATE OR REPLACE VIEW pipeline_metrics AS
SELECT
    COUNT(*) as total_images,
    COUNT(*) FILTER (WHERE processed = TRUE) as completed_images,
    COUNT(*) FILTER (WHERE processed = FALSE) as pending_images,
    COUNT(*) FILTER (WHERE segmentation_status = 'failed' OR preprocessing_status = 'failed') as failed_images,
    COUNT(*) FILTER (WHERE processing_started_at IS NULL) as queued_images,
    COUNT(*) FILTER (WHERE processing_started_at IS NOT NULL AND processing_completed_at IS NULL) as processing_images,
    AVG(CASE
        WHEN processing_completed_at IS NOT NULL AND processing_started_at IS NOT NULL
        THEN EXTRACT(EPOCH FROM (processing_completed_at - processing_started_at))
        ELSE NULL
    END) as average_processing_time_seconds,
    MAX(attempt_count) as max_retry_attempts,
    DATE_TRUNC('hour', created_at) as time_bucket
FROM processed_images
GROUP BY DATE_TRUNC('hour', created_at)
ORDER BY time_bucket DESC;

-- View for identifying bottlenecks
CREATE OR REPLACE VIEW pipeline_bottlenecks AS
SELECT
    segmentation_status,
    preprocessing_status,
    COUNT(*) as image_count,
    MAX(created_at) as oldest_task,
    MIN(created_at) as newest_task,
    AVG(attempt_count) as average_attempts
FROM processed_images
WHERE processed = FALSE
GROUP BY segmentation_status, preprocessing_status
ORDER BY image_count DESC;

-- Grant appropriate permissions (adjust based on your user setup)
-- GRANT SELECT, INSERT, UPDATE ON processed_images TO app;
-- GRANT SELECT ON pipeline_metrics TO app;
-- GRANT SELECT ON pipeline_bottlenecks TO app;
