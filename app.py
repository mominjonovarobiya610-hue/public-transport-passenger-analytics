import csv
import hmac
import io
import json
import mimetypes
import os
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

from database import BASE, connect, initialize, seed

initialize()
seed()


def as_dict(row):
    return dict(row)


def integer(value, field, lowest=1, highest=100000):
    try:
        n = int(value)
    except (ValueError, TypeError):
        raise ValueError(f'{field} to‘g‘ri son bo‘lishi kerak.')
    if not lowest <= n <= highest:
        raise ValueError(f'{field} {lowest} va {highest} oralig‘ida bo‘lishi kerak.')
    return n


def required_text(value, field, length=90):
    s = str(value or '').strip()
    if not s or len(s) > length:
        raise ValueError(f'{field} maydoni to‘ldirilishi kerak (1–{length} belgi).')
    return s


def date_value(value, field):
    try:
        return date.fromisoformat(str(value)).isoformat()
    except (TypeError, ValueError):
        raise ValueError(f'{field} sanasi YYYY-MM-DD shaklida bo‘lishi kerak.')


def dashboard(query):
    end = date_value(query.get('to', [date.today().isoformat()])[0], 'Tugash')
    begin = date_value(query.get('from', [(date.fromordinal(date.fromisoformat(end).toordinal() - 6)).isoformat()])[0], 'Boshlanish')
    if begin > end:
        raise ValueError('Boshlanish sanasi tugash sanasidan keyin bo‘lmasligi kerak.')
    route_filter = query.get('route_id', [''])[0]
    route_id = integer(route_filter, 'Yo‘nalish') if route_filter else None
    with connect() as db:
        rows = db.execute('''SELECT t.id,t.service_date,t.departure_time,t.status,t.route_id,
            r.code,r.name,r.color,v.fleet_no,v.capacity,
            rs.stop_order,pc.boarded,pc.alighted
            FROM trips t JOIN routes r ON r.id=t.route_id
            JOIN vehicles v ON v.id=t.vehicle_id
            LEFT JOIN passenger_counts pc ON pc.trip_id=t.id
            LEFT JOIN route_stops rs ON rs.route_id=t.route_id AND rs.stop_id=pc.stop_id
            WHERE t.service_date BETWEEN ? AND ? AND (? IS NULL OR t.route_id=?)
            ORDER BY t.service_date,t.departure_time,t.id,rs.stop_order''',
            (begin, end, route_id, route_id)).fetchall()
    trips = {}
    for r in rows:
        if r['id'] not in trips:
            trips[r['id']] = {'id': r['id'], 'date': r['service_date'], 'time': r['departure_time'],
                              'route_id': r['route_id'], 'route': r['name'], 'code': r['code'],
                              'color': r['color'], 'vehicle': r['fleet_no'], 'capacity': r['capacity'],
                              'status': r['status'], 'boarding': 0, 'alighting': 0,
                              'peak': 0, 'load': 0, 'has_counts': False}
        trip = trips[r['id']]
        if r['stop_order'] is not None:
            trip['has_counts'] = True
            trip['boarding'] += r['boarded']
            trip['alighting'] += r['alighted']
            trip['load'] += r['boarded'] - r['alighted']
            trip['peak'] = max(trip['peak'], trip['load'])
    counted = [t for t in trips.values() if t['has_counts']]
    daily = Counter()
    hourly = Counter()
    by_route = {}
    for t in counted:
        daily[t['date']] += t['boarding']
        hourly[t['time'][:2]] += t['boarding']
        info = by_route.setdefault(t['route_id'], {'route_id': t['route_id'], 'name': t['route'], 'code': t['code'], 'color': t['color'], 'passengers': 0, 'trips': 0})
        info['passengers'] += t['boarding']
        info['trips'] += 1
    mean_occupancy = round(sum(t['peak'] / t['capacity'] for t in counted) * 100 / len(counted), 1) if counted else 0
    busiest_hour = max(hourly, key=lambda x: hourly[x]) + ':00' if hourly else '—'
    recent = sorted(trips.values(), key=lambda t: (t['date'], t['time'], t['id']), reverse=True)[:9]
    return {'dates': {'from': begin, 'to': end},
            'summary': {'passengers': sum(t['boarding'] for t in counted), 'trips': len(counted),
                        'occupancy': mean_occupancy, 'peak_hour': busiest_hour, 'routes': len(by_route)},
            'daily': [{'date': day, 'passengers': total} for day, total in sorted(daily.items())],
            'hourly': [{'hour': f'{hour}:00', 'passengers': total} for hour, total in sorted(hourly.items())],
            'routes': sorted(by_route.values(), key=lambda x: x['passengers'], reverse=True),
            'recent': recent}


def routes_list():
    with connect() as db:
        result = []
        for r in db.execute('SELECT * FROM routes ORDER BY code').fetchall():
            route = as_dict(r)
            route['vehicles'] = db.execute('SELECT COUNT(*) FROM vehicles WHERE route_id=?', (r['id'],)).fetchone()[0]
            route['stops'] = [as_dict(s) for s in db.execute('''SELECT s.id,s.name,rs.stop_order FROM route_stops rs JOIN stops s ON s.id=rs.stop_id WHERE rs.route_id=? ORDER BY rs.stop_order''', (r['id'],)).fetchall()]
            result.append(route)
        return result


def trips_list(query):
    route_raw = query.get('route_id', [''])[0]
    route_id = integer(route_raw, 'Yo‘nalish') if route_raw else None
    with connect() as db:
        rows = db.execute('''SELECT t.id,t.service_date,t.departure_time,t.status,
                t.route_id,t.vehicle_id,r.name AS route,r.code,v.fleet_no AS vehicle,
                COALESCE(SUM(pc.boarded),0) AS passengers
                FROM trips t JOIN routes r ON r.id=t.route_id JOIN vehicles v ON v.id=t.vehicle_id
                LEFT JOIN passenger_counts pc ON pc.trip_id=t.id
                WHERE (? IS NULL OR t.route_id=?)
                GROUP BY t.id ORDER BY t.service_date DESC,t.departure_time DESC,t.id DESC LIMIT 150''',
                (route_id, route_id)).fetchall()
        return [as_dict(r) for r in rows]


def counts_list(trip_id):
    with connect() as db:
        trip = db.execute('SELECT id,route_id FROM trips WHERE id=?', (trip_id,)).fetchone()
        if not trip:
            raise ValueError('Qatnov topilmadi.')
        return [as_dict(r) for r in db.execute('''SELECT s.id AS stop_id,s.name,rs.stop_order,
                   COALESCE(pc.boarded,0) AS boarded,COALESCE(pc.alighted,0) AS alighted
                   FROM route_stops rs JOIN stops s ON s.id=rs.stop_id
                   LEFT JOIN passenger_counts pc ON pc.stop_id=s.id AND pc.trip_id=?
                   WHERE rs.route_id=? ORDER BY rs.stop_order''', (trip_id, trip['route_id'])).fetchall()]


def create_route(data):
    code = required_text(data.get('code'), 'Yo‘nalish raqami', 12)
    name = required_text(data.get('name'), 'Nomi')
    origin = required_text(data.get('origin'), 'Boshlang‘ich bekat')
    destination = required_text(data.get('destination'), 'Oxirgi bekat')
    if origin == destination:
        raise ValueError('Boshlang‘ich va oxirgi bekatlar turlicha bo‘lishi kerak.')
    with connect() as db:
        cur = db.execute('INSERT INTO routes(code,name,origin,destination) VALUES(?,?,?,?)', (code, name, origin, destination))
        for order, stop_name in enumerate((origin, destination), 1):
            db.execute('INSERT OR IGNORE INTO stops(name) VALUES(?)', (stop_name,))
            stop_id = db.execute('SELECT id FROM stops WHERE name=?', (stop_name,)).fetchone()[0]
            db.execute('INSERT INTO route_stops(route_id,stop_id,stop_order) VALUES(?,?,?)', (cur.lastrowid, stop_id, order))
        return {'id': cur.lastrowid, 'message': 'Yo‘nalish qo‘shildi.'}


def create_vehicle(data):
    route_id = integer(data.get('route_id'), 'Yo‘nalish')
    fleet_no = required_text(data.get('fleet_no'), 'Avtobus raqami', 24)
    capacity = integer(data.get('capacity'), 'Sig‘im', 1, 300)
    with connect() as db:
        if not db.execute('SELECT 1 FROM routes WHERE id=?', (route_id,)).fetchone():
            raise ValueError('Yo‘nalish topilmadi.')
        cur = db.execute('INSERT INTO vehicles(fleet_no,capacity,route_id) VALUES(?,?,?)', (fleet_no, capacity, route_id))
        return {'id': cur.lastrowid, 'message': 'Transport qo‘shildi.'}


def create_trip(data):
    route_id = integer(data.get('route_id'), 'Yo‘nalish')
    vehicle_id = integer(data.get('vehicle_id'), 'Transport')
    service_date = date_value(data.get('service_date'), 'Qatnov')
    departure_time = required_text(data.get('departure_time'), 'Jo‘nash vaqti', 5)
    if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', departure_time):
        raise ValueError('Vaqt HH:MM shaklida bo‘lishi kerak.')
    with connect() as db:
        vehicle = db.execute('SELECT 1 FROM vehicles WHERE id=? AND route_id=?', (vehicle_id, route_id)).fetchone()
        if not vehicle:
            raise ValueError('Transport tanlangan yo‘nalishga tegishli emas.')
        cur = db.execute('INSERT INTO trips(route_id,vehicle_id,service_date,departure_time) VALUES(?,?,?,?)', (route_id, vehicle_id, service_date, departure_time))
        return {'id': cur.lastrowid, 'message': 'Qatnov qo‘shildi.'}


def save_counts(data):
    trip_id = integer(data.get('trip_id'), 'Qatnov')
    stop_id = integer(data.get('stop_id'), 'Bekat')
    boarded = integer(data.get('boarded'), 'Chiqan yo‘lovchilar', 0, 10000)
    alighted = integer(data.get('alighted'), 'Tushgan yo‘lovchilar', 0, 10000)
    with connect() as db:
        trip = db.execute('''SELECT t.route_id,v.capacity FROM trips t JOIN vehicles v ON v.id=t.vehicle_id WHERE t.id=?''', (trip_id,)).fetchone()
        if not trip:
            raise ValueError('Qatnov topilmadi.')
        stops = db.execute('''SELECT rs.stop_id,COALESCE(pc.boarded,0) AS boarded,
            COALESCE(pc.alighted,0) AS alighted FROM route_stops rs
            LEFT JOIN passenger_counts pc ON pc.trip_id=? AND pc.stop_id=rs.stop_id
            WHERE rs.route_id=? ORDER BY rs.stop_order''', (trip_id, trip['route_id'])).fetchall()
        if stop_id not in [s['stop_id'] for s in stops]:
            raise ValueError('Bekat tanlangan yo‘nalishga tegishli emas.')
        occupancy = 0
        for s in stops:
            occupancy += (boarded if s['stop_id'] == stop_id else s['boarded']) - (alighted if s['stop_id'] == stop_id else s['alighted'])
            if not 0 <= occupancy <= trip['capacity']:
                raise ValueError('Hisob ma’lumotlari transport sig‘imi yoki yo‘lovchilar balansiga mos kelmaydi.')
        db.execute('''INSERT INTO passenger_counts(trip_id,stop_id,boarded,alighted) VALUES(?,?,?,?)
            ON CONFLICT(trip_id,stop_id) DO UPDATE SET boarded=excluded.boarded,alighted=excluded.alighted,recorded_at=CURRENT_TIMESTAMP''',
            (trip_id, stop_id, boarded, alighted))
        db.execute("UPDATE trips SET status='yakunlangan' WHERE id=?", (trip_id,))
        return {'message': 'Yo‘lovchilar soni saqlandi.'}


def export_csv(query):
    d = dashboard(query)
    begin, end = d['dates']['from'], d['dates']['to']
    route_raw = query.get('route_id', [''])[0]
    route_id = int(route_raw) if route_raw else None
    with connect() as db:
        rows = db.execute('''SELECT t.service_date,t.departure_time,r.code,r.name,v.fleet_no,s.name,
                    pc.boarded,pc.alighted
                    FROM passenger_counts pc
                    JOIN trips t ON t.id=pc.trip_id
                    JOIN routes r ON r.id=t.route_id
                    JOIN vehicles v ON v.id=t.vehicle_id
                    JOIN stops s ON s.id=pc.stop_id
                    JOIN route_stops rs ON rs.route_id=t.route_id AND rs.stop_id=s.id
                    WHERE t.service_date BETWEEN ? AND ? AND (? IS NULL OR t.route_id=?)
                    ORDER BY t.service_date,t.departure_time,r.code,rs.stop_order''',
                    (begin, end, route_id, route_id)).fetchall()
    out = io.StringIO()
    out.write('\ufeff')
    writer = csv.writer(out)
    writer.writerow(['Sana','Jo‘nash','Yo‘nalish','Yo‘nalish nomi','Transport','Bekat','Chiqqan','Tushgan'])
    writer.writerows(tuple(row) for row in rows)
    return out.getvalue().encode('utf-8')


def response(start_response, body, status='200 OK', content_type='application/json; charset=utf-8', extra=None):
    raw = json.dumps(body, ensure_ascii=False).encode('utf-8') if isinstance(body, (dict,list)) else body
    headers = [('Content-Type', content_type), ('Content-Length', str(len(raw))), ('Cache-Control', 'no-store'),
               ('X-Content-Type-Options', 'nosniff'), ('X-Frame-Options', 'DENY')]
    if extra:
        headers.extend(extra)
    start_response(status, headers)
    return [raw]


def application(environ, start_response):
    method = environ.get('REQUEST_METHOD', 'GET').upper()
    path = environ.get('PATH_INFO', '/')
    query = parse_qs(environ.get('QUERY_STRING', ''), keep_blank_values=True)
    try:
        if method == 'GET' and path in ('/', '/static/app.js', '/static/style.css'):
            files = {'/': BASE / 'templates' / 'index.html', '/static/app.js': BASE / 'static' / 'app.js', '/static/style.css': BASE / 'static' / 'style.css'}
            file = files[path]
            mime = 'text/html; charset=utf-8' if path == '/' else ('text/javascript; charset=utf-8' if path.endswith('.js') else 'text/css; charset=utf-8')
            return response(start_response, file.read_bytes(), content_type=mime)
        if method == 'GET' and path == '/api/health':
            return response(start_response, {'status': 'ok'})
        if method == 'GET' and path == '/api/dashboard':
            return response(start_response, dashboard(query))
        if method == 'GET' and path == '/api/routes':
            return response(start_response, routes_list())
        if method == 'GET' and path == '/api/vehicles':
            with connect() as db:
                return response(start_response, [as_dict(x) for x in db.execute('SELECT * FROM vehicles ORDER BY fleet_no').fetchall()])
        if method == 'GET' and path == '/api/trips':
            return response(start_response, trips_list(query))
        if method == 'GET' and path == '/api/counts':
            return response(start_response, counts_list(integer(query.get('trip_id', [''])[0], 'Qatnov')))
        if method == 'GET' and path == '/api/export.csv':
            return response(start_response, export_csv(query), content_type='text/csv; charset=utf-8', extra=[('Content-Disposition', 'attachment; filename="yolovchilar_hisoboti.csv"')])
        if method == 'POST' and path in ('/api/routes','/api/vehicles','/api/trips','/api/counts'):
            token = os.environ.get('ADMIN_TOKEN', '')
            if token and not hmac.compare_digest(environ.get('HTTP_X_ADMIN_TOKEN', ''), token):
                return response(start_response, {'error': 'Ma’lumot kiritish uchun ruxsat yo‘q.'}, '403 Forbidden')
            size = integer(environ.get('CONTENT_LENGTH', 0), 'So‘rov hajmi', 1, 65536)
            if 'application/json' not in environ.get('CONTENT_TYPE', ''):
                raise ValueError('JSON ma’lumot yuborilishi kerak.')
            try:
                data = json.loads(environ['wsgi.input'].read(size))
            except (ValueError, UnicodeDecodeError):
                raise ValueError('JSON ma’lumoti noto‘g‘ri.')
            if not isinstance(data, dict):
                raise ValueError('Ma’lumot obyekt shaklida bo‘lishi kerak.')
            actions = {'/api/routes':create_route,'/api/vehicles':create_vehicle,'/api/trips':create_trip,'/api/counts':save_counts}
            return response(start_response, actions[path](data), '201 Created')
        return response(start_response, {'error': 'Sahifa topilmadi.'}, '404 Not Found')
    except ValueError as ex:
        return response(start_response, {'error': str(ex)}, '400 Bad Request')
    except sqlite3.IntegrityError:
        return response(start_response, {'error': 'Bunday ma’lumot allaqachon mavjud yoki aloqalar noto‘g‘ri.'}, '409 Conflict')
    except Exception:
        return response(start_response, {'error': 'Serverda xatolik yuz berdi.'}, '500 Internal Server Error')


if __name__ == '__main__':
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', '8000'))
    print(f'Tizim ishga tushdi: http://{host}:{port}')
    with make_server(host, port, application) as server:
        server.serve_forever()
