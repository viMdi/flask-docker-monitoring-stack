CREATE TABLE IF NOT EXISTS users (
      id SERIAL PRIMARY KEY,
      username VARCHAR(64) UNIQUE NOT NULL,
      password_hash TEXT NOT NULL,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE monitors ADD COLUMN IF NOT EXISTS user_id INTEGER;

DO $$
BEGIN
    ALTER TABLE monitors
        ADD CONSTRAINT fk_monitors_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

ALTER TABLE monitors DROP CONSTRAINT IF EXISTS monitors_url_key;

DO $$
BEGIN
    ALTER TABLE monitors
        ADD CONSTRAINT uq_monitors_user_url
        UNIQUE (user_id, url);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;
