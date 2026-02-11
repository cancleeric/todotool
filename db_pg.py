"""PostgreSQL database layer for TodoTool."""
try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    raise RuntimeError("psycopg2 not installed")
import os

PG_CONFIG = {
    'host': os.environ.get('HS_PG_HOST', 'host.docker.internal'),
    'port': int(os.environ.get('HS_PG_PORT', '5432')),
    'database': os.environ.get('HS_PG_DB', ''),
    'user': os.environ.get('HS_PG_USER', ''),
    'password': os.environ.get('HS_PG_PASSWORD', ''),
}

def _pg_connect(config=None):
    cfg = config or PG_CONFIG
    conn = psycopg2.connect(
        host=cfg.get('pg_host', cfg.get('host', 'localhost')),
        port=cfg.get('pg_port', cfg.get('port', 5432)),
        database=cfg.get('pg_database', cfg.get('database', '')),
        user=cfg.get('pg_user', cfg.get('user', '')),
        password=cfg.get('pg_password', cfg.get('password', '')),
    )
    conn.autocommit = True
    return conn


import os
import hashlib
import secrets

from datetime import date, datetime, timedelta



def normalize_date(d):
    """Normalize a date string to YYYY-MM-DD format."""
    if not d:
        return d
    try:
        return datetime.strptime(d.strip(), '%Y-%m-%d').strftime('%Y-%m-%d')
    except ValueError:
        return d


def get_conn(db_path=None):
    conn = _pg_connect(config)
    
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(config=None):
    conn = get_conn(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS todo_users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS todo_todos (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'done')),
            priority TEXT NOT NULL DEFAULT 'medium' CHECK(priority IN ('high', 'medium', 'low')),
            due_date TEXT,
            note TEXT DEFAULT '',
            created_by TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME
        );

        CREATE TABLE IF NOT EXISTS todo_tags (
            todo_id INTEGER NOT NULL REFERENCES todo_todos(id) ON DELETE CASCADE,
            tag TEXT NOT NULL,
            UNIQUE(todo_id, tag)
        );

        CREATE TABLE IF NOT EXISTS todo_history (
            id SERIAL PRIMARY KEY,
            todo_id INTEGER NOT NULL,
            field TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            changed_by TEXT DEFAULT '',
            changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (todo_id) REFERENCES todo_todos(id)
        );

        CREATE INDEX IF NOT EXISTS idx_todos_status ON todo_todos(status);
        CREATE INDEX IF NOT EXISTS idx_todos_priority ON todo_todos(priority);
        CREATE INDEX IF NOT EXISTS idx_todos_due_date ON todo_todos(due_date);
        CREATE INDEX IF NOT EXISTS idx_todo_tags_tag ON todo_tags(tag);
        CREATE INDEX IF NOT EXISTS idx_todo_history_todo ON todo_history(todo_id);
    """)
    conn.commit()
    return conn


# --- Auth ---

def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return hashed.hex(), salt


def create_user(conn, username, password):
    pw_hash, salt = hash_password(password)
    try:
        conn.execute("INSERT INTO todo_users (username, password_hash, salt) VALUES (%s, %s, %s)",
                     (username, pw_hash, salt))
        conn.commit()
        return True
    except psycopg2.IntegrityError:
        return False


def verify_user(conn, username, password):
    row = conn.execute("SELECT password_hash, salt FROM todo_users WHERE username = %s",
                       (username,)).fetchone()
    if not row:
        return False
    pw_hash, _ = hash_password(password, row['salt'])
    return pw_hash == row['password_hash']


# --- Todos ---

def add_todo(conn, title, priority='medium', due_date=None, note='', created_by='', tags=None):
    due_date = normalize_date(due_date)
    cur = conn.execute(
        "INSERT INTO todo_todos (title, priority, due_date, note, created_by) VALUES (%s, %s, %s, %s, %s)",
        (title, priority, due_date, note, created_by))
    todo_id = cur.lastrowid
    if tags:
        for tag in tags:
            try:
                conn.execute("INSERT INTO todo_tags (todo_id, tag) VALUES (%s, %s)", (todo_id, tag))
            except psycopg2.IntegrityError:
                pass
    conn.commit()
    return todo_id


def _log_change(conn, todo_id, field, old_value, new_value, changed_by=''):
    if str(old_value) != str(new_value):
        conn.execute(
            "INSERT INTO todo_history (todo_id, field, old_value, new_value, changed_by) VALUES (%s, %s, %s, %s, %s)",
            (todo_id, field, str(old_value) if old_value is not None else '', 
             str(new_value) if new_value is not None else '', changed_by))


def edit_todo(conn, todo_id, title=None, priority=None, due_date=None, note=None, tags=None, changed_by=''):
    old = get_todo(conn, todo_id)
    if not old:
        return
    updates = []
    params = []
    if title is not None and title != old['title']:
        _log_change(conn, todo_id, 'title', old['title'], title, changed_by)
        updates.append("title = %s")
        params.append(title)
    if priority is not None and priority != old['priority']:
        _log_change(conn, todo_id, 'priority', old['priority'], priority, changed_by)
        updates.append("priority = %s")
        params.append(priority)
    if due_date is not None:
        new_due = normalize_date(due_date) if due_date != '' else None
        if new_due != old['due_date']:
            _log_change(conn, todo_id, 'due_date', old['due_date'], new_due, changed_by)
            updates.append("due_date = %s")
            params.append(new_due)
    if note is not None and note != old['note']:
        _log_change(conn, todo_id, 'note', old['note'], note, changed_by)
        updates.append("note = %s")
        params.append(note)
    if updates:
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(todo_id)
        conn.execute(f"UPDATE todo_todos SET {', '.join(updates)} WHERE id = %s", params)
    if tags is not None:
        old_tags = sorted(get_todo_tags(conn, todo_id))
        new_tags = sorted(tags)
        if old_tags != new_tags:
            _log_change(conn, todo_id, 'tags', ','.join(old_tags), ','.join(new_tags), changed_by)
            conn.execute("DELETE FROM todo_tags WHERE todo_id = %s", (todo_id,))
            for tag in tags:
                try:
                    conn.execute("INSERT INTO todo_tags (todo_id, tag) VALUES (%s, %s)", (todo_id, tag))
                except psycopg2.IntegrityError:
                    pass
    conn.commit()


def mark_done(conn, todo_id, changed_by=''):
    old = get_todo(conn, todo_id)
    if old and old['status'] != 'done':
        _log_change(conn, todo_id, 'status', 'pending', 'done', changed_by)
    conn.execute("UPDATE todo_todos SET status = 'done', completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                 (todo_id,))
    conn.commit()


def get_history(conn, todo_id):
    return conn.execute(
        "SELECT * FROM todo_history WHERE todo_id = %s ORDER BY changed_at ASC",
        (todo_id,)).fetchall()


def get_todo(conn, todo_id):
    return conn.execute("SELECT * FROM todo_todos WHERE id = %s", (todo_id,)).fetchone()


def get_todo_tags(conn, todo_id):
    rows = conn.execute("SELECT tag FROM todo_tags WHERE todo_id = %s", (todo_id,)).fetchall()
    return [r['tag'] for r in rows]


def list_todos(conn, status=None, tag=None, priority=None, due_date=None, limit=50):
    sql = "SELECT DISTINCT t.* FROM todo_todos t"
    joins = []
    where = []
    params = []
    if tag:
        joins.append(" JOIN todo_tags tt ON t.id = tt.todo_id")
        where.append("tt.tag = %s")
        params.append(tag)
    sql += ''.join(joins)
    if status:
        where.append("t.status = %s")
        params.append(status)
    if priority:
        where.append("t.priority = %s")
        params.append(priority)
    if due_date:
        where.append("t.due_date <= %s")
        params.append(due_date)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY t.id ASC LIMIT %s"
    params.append(limit)
    return conn.execute(sql, params).fetchall()


def list_due_within(conn, days):
    today = date.today().strftime('%Y-%m-%d')
    end = (date.today() + timedelta(days=days)).strftime('%Y-%m-%d')
    return conn.execute(
        "SELECT * FROM todo_todos WHERE status = 'pending' AND due_date IS NOT NULL AND due_date >= %s AND due_date <= %s ORDER BY due_date ASC",
        (today, end)).fetchall()


def list_all_tags(conn):
    return conn.execute("SELECT tag, COUNT(*) as count FROM todo_tags GROUP BY tag ORDER BY count DESC").fetchall()
