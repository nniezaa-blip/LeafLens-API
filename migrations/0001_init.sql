-- Lextari API schema.
--
-- The auth Worker owns `users` and refresh state; this Worker only owns the
-- device → user mapping. `favoriot_device_id` stores the FavorIoT
-- `device_developer_id`, for example `Agrilink_1_device@anwarzain`.

CREATE TABLE user_devices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  favoriot_device_id TEXT NOT NULL UNIQUE,
  device_name TEXT NOT NULL,
  device_type TEXT NOT NULL DEFAULT 'lextari-env',
  mac_address TEXT UNIQUE,
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX idx_user_devices_user ON user_devices(user_id);
