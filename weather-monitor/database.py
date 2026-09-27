import sqlite3
from datetime import datetime, timedelta
from contextlib import contextmanager

DB_PATH = "weather.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS weather (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                temp REAL,
                humidity REAL,
                wind_speed REAL,
                weather_code INTEGER,
                weather_desc TEXT,
                pressure REAL
            );

            CREATE TABLE IF NOT EXISTS air_quality (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                pm10 REAL,
                pm2_5 REAL,
                no2 REAL,
                so2 REAL,
                o3 REAL,
                co REAL,
                aqi INTEGER
            );

            CREATE TABLE IF NOT EXISTS uv_index (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                uv_max REAL,
                uv_description TEXT
            );

            CREATE TABLE IF NOT EXISTS radiation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                radiation_value REAL,
                unit TEXT DEFAULT 'μR/h',
                source TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_weather_ts ON weather(timestamp);
            CREATE INDEX IF NOT EXISTS idx_air_ts ON air_quality(timestamp);
            CREATE INDEX IF NOT EXISTS idx_uv_ts ON uv_index(timestamp);
            CREATE INDEX IF NOT EXISTS idx_rad_ts ON radiation(timestamp);
        """)


def insert_weather(data: dict):
    with get_db() as conn:
        conn.execute(
            """INSERT INTO weather (timestamp, temp, humidity, wind_speed,
               weather_code, weather_desc, pressure)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                data["timestamp"],
                data.get("temp"),
                data.get("humidity"),
                data.get("wind_speed"),
                data.get("weather_code"),
                data.get("weather_desc"),
                data.get("pressure"),
            ),
        )


def insert_air_quality(data: dict):
    with get_db() as conn:
        conn.execute(
            """INSERT INTO air_quality (timestamp, pm10, pm2_5, no2, so2, o3, co, aqi)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data["timestamp"],
                data.get("pm10"),
                data.get("pm2_5"),
                data.get("no2"),
                data.get("so2"),
                data.get("o3"),
                data.get("co"),
                data.get("aqi"),
            ),
        )


def insert_uv(data: dict):
    with get_db() as conn:
        conn.execute(
            """INSERT INTO uv_index (timestamp, uv_max, uv_description)
               VALUES (?, ?, ?)""",
            (
                data["timestamp"],
                data.get("uv_max"),
                data.get("uv_description"),
            ),
        )


def insert_radiation(data: dict):
    with get_db() as conn:
        conn.execute(
            """INSERT INTO radiation (timestamp, radiation_value, unit, source)
               VALUES (?, ?, ?, ?)""",
            (
                data["timestamp"],
                data.get("radiation_value"),
                data.get("unit", "μR/h"),
                data.get("source"),
            ),
        )


def get_latest_weather():
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM weather ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def get_latest_air():
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM air_quality ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def get_latest_uv():
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM uv_index ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def get_latest_radiation():
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM radiation ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def get_today_weather():
    today = datetime.now().strftime("%Y-%m-%d")
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM weather WHERE timestamp LIKE ? ORDER BY timestamp",
            (f"{today}%",),
        ).fetchall()
        return [dict(r) for r in rows]


def get_today_air():
    today = datetime.now().strftime("%Y-%m-%d")
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM air_quality WHERE timestamp LIKE ? ORDER BY timestamp",
            (f"{today}%",),
        ).fetchall()
        return [dict(r) for r in rows]


def get_history(table: str, hours: int = 24):
    since = (datetime.now() - timedelta(hours=hours)).isoformat()
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM {table} WHERE timestamp >= ? ORDER BY timestamp",
            (since,),
        ).fetchall()
        return [dict(r) for r in rows]


if __name__ == "__main__":
    init_db()
    print("Database initialized.")
