PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS routes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    color TEXT NOT NULL DEFAULT '#857456',
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    district TEXT NOT NULL DEFAULT 'Andijon'
);

CREATE TABLE IF NOT EXISTS route_stops (
    route_id INTEGER NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
    stop_id INTEGER NOT NULL REFERENCES stops(id) ON DELETE RESTRICT,
    stop_order INTEGER NOT NULL CHECK (stop_order > 0),
    PRIMARY KEY (route_id, stop_id),
    UNIQUE (route_id, stop_order)
);

CREATE TABLE IF NOT EXISTS vehicles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fleet_no TEXT NOT NULL UNIQUE,
    capacity INTEGER NOT NULL CHECK (capacity BETWEEN 1 AND 300),
    route_id INTEGER NOT NULL REFERENCES routes(id) ON DELETE RESTRICT,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1))
);

CREATE TABLE IF NOT EXISTS trips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    route_id INTEGER NOT NULL REFERENCES routes(id) ON DELETE RESTRICT,
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE RESTRICT,
    service_date TEXT NOT NULL,
    departure_time TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'rejalashtirilgan' CHECK (status IN ('rejalashtirilgan','yakunlangan')),
    UNIQUE (vehicle_id, service_date, departure_time)
);

CREATE TABLE IF NOT EXISTS passenger_counts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    stop_id INTEGER NOT NULL REFERENCES stops(id) ON DELETE RESTRICT,
    boarded INTEGER NOT NULL DEFAULT 0 CHECK (boarded >= 0),
    alighted INTEGER NOT NULL DEFAULT 0 CHECK (alighted >= 0),
    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (trip_id, stop_id)
);

CREATE INDEX IF NOT EXISTS ix_trips_date ON trips(service_date);
CREATE INDEX IF NOT EXISTS ix_trips_route_date ON trips(route_id, service_date);
CREATE INDEX IF NOT EXISTS ix_counts_trip ON passenger_counts(trip_id);
