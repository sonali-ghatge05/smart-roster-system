import sqlite3

DB_PATH = "roster.db"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS pods (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    );

    CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        role TEXT NOT NULL,                  -- 'Pod Lead' or 'Specialist'
        pod_id INTEGER NOT NULL,
        preferred_weekly_off INTEGER DEFAULT 6, -- 0=Mon, 6=Sun
        is_active INTEGER DEFAULT 1,
        FOREIGN KEY (pod_id) REFERENCES pods(id)
    );

    CREATE TABLE IF NOT EXISTS brands (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        pod_id INTEGER NOT NULL,
        FOREIGN KEY (pod_id) REFERENCES pods(id)
    );

    CREATE TABLE IF NOT EXISTS processes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,           -- 'CS', 'ACC', 'NDR', 'RET'
        name TEXT NOT NULL
    );

    -- Decoupled operating calendar & coverage rules per (Brand, Process)
    CREATE TABLE IF NOT EXISTS brand_process_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        brand_id INTEGER NOT NULL,
        process_id INTEGER NOT NULL,
        calendar_type TEXT NOT NULL CHECK(calendar_type IN (
            '365_DAYS', 
            'DAILY_EXCEPT_HOLIDAYS', 
            'NO_SUNDAYS_OR_HOLIDAYS'
        )),
        min_staff INTEGER NOT NULL DEFAULT 1,
        UNIQUE(brand_id, process_id),
        FOREIGN KEY (brand_id) REFERENCES brands(id),
        FOREIGN KEY (process_id) REFERENCES processes(id)
    );

    -- Resource allocations (supports 1-to-1, 1-to-many, and overlapping assignments)
    CREATE TABLE IF NOT EXISTS assignments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER NOT NULL,
        brand_id INTEGER NOT NULL,
        process_id INTEGER NOT NULL,
        UNIQUE(employee_id, brand_id, process_id),
        FOREIGN KEY (employee_id) REFERENCES employees(id),
        FOREIGN KEY (brand_id) REFERENCES brands(id),
        FOREIGN KEY (process_id) REFERENCES processes(id)
    );

    CREATE TABLE IF NOT EXISTS public_holidays (
        date TEXT PRIMARY KEY,               -- 'YYYY-MM-DD'
        name TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS leaves (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER NOT NULL,
        date TEXT NOT NULL,                  -- 'YYYY-MM-DD'
        leave_type TEXT NOT NULL CHECK(leave_type IN ('PLANNED_LEAVE', 'COMP_OFF')),
        status TEXT NOT NULL DEFAULT 'APPROVED',
        UNIQUE(employee_id, date),
        FOREIGN KEY (employee_id) REFERENCES employees(id)
    );

    CREATE TABLE IF NOT EXISTS roster_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER NOT NULL,
        date TEXT NOT NULL,                  -- 'YYYY-MM-DD'
        status TEXT NOT NULL CHECK(status IN (
            'WORKING', 'WEEKLY_OFF', 'PUBLIC_HOLIDAY', 'PLANNED_LEAVE', 'COMP_OFF'
        )),
        is_manual_override INTEGER DEFAULT 0,
        notes TEXT DEFAULT '',
        UNIQUE(employee_id, date),
        FOREIGN KEY (employee_id) REFERENCES employees(id)
    );

    CREATE TABLE IF NOT EXISTS temporary_covers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        brand_id INTEGER NOT NULL,
        process_id INTEGER NOT NULL,
        backup_employee_id INTEGER NOT NULL,
        UNIQUE(date, brand_id, process_id, backup_employee_id),
        FOREIGN KEY (brand_id) REFERENCES brands(id),
        FOREIGN KEY (process_id) REFERENCES processes(id),
        FOREIGN KEY (backup_employee_id) REFERENCES employees(id)
    );

    """)


    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")