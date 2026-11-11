-- Lextari API schema.
--
-- The auth Worker owns `users` and refresh state; this Worker only owns the
-- device → user mapping. `tb_device_id` is retained as the column name but
-- now stores the platform's device identifier (FavorIoT
-- `device_developer_id`, e.g. `deviceDefault@user`).

CREATE TABLE user_devices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  tb_device_id TEXT NOT NULL UNIQUE,
  device_name TEXT NOT NULL,
  device_type TEXT NOT NULL DEFAULT 'lextari-env',
  mac_address TEXT UNIQUE,
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX idx_user_devices_user ON user_devices(user_id);
