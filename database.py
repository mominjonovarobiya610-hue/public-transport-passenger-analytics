import os
from contextlib import contextmanager
import random
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get('TRANSPORT_DB', str(BASE / 'transport.db')))


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(DB_PATH), timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    db.execute('PRAGMA busy_timeout = 15000')
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def initialize():
    with connect() as db:
        db.executescript((BASE / 'schema.sql').read_text(encoding='utf-8'))
        db.commit()


def seed(force=False):
    initialize()
    rng = random.Random(312)
    with connect() as db:
        count = db.execute('SELECT COUNT(*) FROM routes').fetchone()[0]
        if count and not force:
            return False
        if force:
            for tab in ('passenger_counts', 'trips', 'vehicles', 'route_stops', 'routes', 'stops'):
                db.execute(f'DELETE FROM {tab}')
        routes = [
            ('01', 'Markaz — Universitet', 'Markaziy bekat', 'Universitet', '#9a7659'),
            ('05', 'Bozor — Shifoxona', 'Markaziy bozor', 'Shifoxona', '#727d62'),
            ('12', 'Vokzal — Bog‘ishamol', 'Temiryo‘l vokzali', 'Bog‘ishamol', '#b28c43'),
            ('18', 'Park — Sport majmuasi', 'Shahar bog‘i', 'Sport majmuasi', '#8d777f')
        ]
        for code, name, origin, destination, color in routes:
            db.execute('INSERT INTO routes(code,name,origin,destination,color) VALUES(?,?,?,?,?)', (code, name, origin, destination, color))
        stop_map = {
            '01': ['Markaziy bekat', 'Kutubxona', 'Universitet'],
            '05': ['Markaziy bozor', 'Madaniyat uyi', 'Shifoxona'],
            '12': ['Temiryo‘l vokzali', 'Yangi ko‘cha', 'Bog‘ishamol'],
            '18': ['Shahar bog‘i', 'Sport maktabi', 'Sport majmuasi']
        }
        for code, names in stop_map.items():
            route_id = db.execute('SELECT id FROM routes WHERE code=?', (code,)).fetchone()['id']
            for order, name in enumerate(names, 1):
                db.execute('INSERT OR IGNORE INTO stops(name) VALUES(?)', (name,))
                stop_id = db.execute('SELECT id FROM stops WHERE name=?', (name,)).fetchone()['id']
                db.execute('INSERT INTO route_stops(route_id,stop_id,stop_order) VALUES(?,?,?)', (route_id, stop_id, order))
        route_rows = db.execute('SELECT id,code FROM routes ORDER BY id').fetchall()
        for route in route_rows:
            for suffix in ('1', '2'):
                db.execute('INSERT INTO vehicles(fleet_no,capacity,route_id) VALUES(?,?,?)', (f'A-{route["code"]}{suffix}', 45 if suffix == '1' else 36, route['id']))
        day_start = date.today() - timedelta(days=29)
        for d in range(30):
            current = (day_start + timedelta(days=d)).isoformat()
            weekday = (day_start + timedelta(days=d)).weekday()
            for route in route_rows:
                vehicles = db.execute('SELECT id,capacity FROM vehicles WHERE route_id=? ORDER BY id', (route['id'],)).fetchall()
                stops = db.execute('SELECT stop_id FROM route_stops WHERE route_id=? ORDER BY stop_order', (route['id'],)).fetchall()
                for hour, minute in [(7, 15), (9, 40), (13, 30), (17, 50)]:
                    vehicle = vehicles[0 if hour in (7, 13) else 1]
                    departure = f'{hour:02}:{minute:02}'
                    db.execute('INSERT INTO trips(route_id,vehicle_id,service_date,departure_time,status) VALUES(?,?,?,?,?)', (route['id'], vehicle['id'], current, departure, 'yakunlangan'))
                    trip_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
                    busy = 1.3 if hour in (7, 17) else 0.8
                    weekend = 0.65 if weekday >= 5 else 1
                    boarding = min(vehicle['capacity'] - 6, max(4, int(rng.randint(11, 29) * busy * weekend)))
                    intermediate_in = rng.randint(1, 7)
                    intermediate_out = rng.randint(2, min(12, boarding))
                    last_out = boarding - intermediate_out + intermediate_in
                    counts = [(boarding, 0), (intermediate_in, intermediate_out), (0, last_out)]
                    for stop, (ins, outs) in zip(stops, counts):
                        db.execute('INSERT INTO passenger_counts(trip_id,stop_id,boarded,alighted) VALUES(?,?,?,?)', (trip_id, stop['stop_id'], ins, outs))
        db.commit()
    return True


if __name__ == '__main__':
    import sys
    seed(force='--reset' in sys.argv)
    print('Ma’lumotlar bazasi tayyor.')
