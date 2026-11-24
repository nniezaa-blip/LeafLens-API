-- Recreate device mappings so the FavorIoT device identifier column replaces
-- the removed ThingsBoard column. Existing mappings are dropped.

DROP TABLE IF EXISTS user_devices;

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
