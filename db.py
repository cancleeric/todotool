"""SQLite database layer for TodoTool."""
import sqlite3
import os
import hashlib
import secrets

from datetime import date, datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), 'todo.db')


def normalize_date(d):
    """Normalize a date string to YYYY-MM-DD format."""
    if not d:
        return d
    try:
        return datetime.strptime(d.strip(), '%Y-%m-%d').strftime('%Y-%m-%d')
    except ValueError:
        return d


def get_conn(db_path=None):
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path=None):
    conn = get_conn(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'done')),
            priority TEXT NOT NULL DEFAULT 'medium' CHECK(priority IN ('high', 'medium', 'low')),
            due_date TEXT,
            note TEXT DEFAULT '',
            created_by TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME
        );

        CREATE TABLE IF NOT EXISTS todo_tags (
            todo_id INTEGER NOT NULL REFERENCES todos(id) ON DELETE CASCADE,
            tag TEXT NOT NULL,
            UNIQUE(todo_id, tag)
        );

        CREATE INDEX IF NOT EXISTS idx_todos_status ON todos(status);
        CREATE INDEX IF NOT EXISTS idx_todos_priority ON todos(priority);
        CREATE INDEX IF NOT EXISTS idx_todos_due_date ON todos(due_date);
        CREATE INDEX IF NOT EXISTS idx_todo_tags_tag ON todo_tags(tag);
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
        conn.execute("INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
                     (username, pw_hash, salt))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def verify_user(conn, username, password):
    row = conn.execute("SELECT password_hash, salt FROM users WHERE username = ?",
                       (username,)).fetchone()
    if not row:
        return False
    pw_hash, _ = hash_password(password, row['salt'])
    return pw_hash == row['password_hash']


# --- Todos ---

def add_todo(conn, title, priority='medium', due_date=None, note='', created_by='', tags=None):
    due_date = normalize_date(due_date)
    cur = conn.execute(
        "INSERT INTO todos (title, priority, due_date, note, created_by) VALUES (?, ?, ?, ?, ?)",
        (title, priority, due_date, note, created_by))
    todo_id = cur.lastrowid
    if tags:
        for tag in tags:
            try:
                conn.execute("INSERT INTO todo_tags (todo_id, tag) VALUES (?, ?)", (todo_id, tag))
            except sqlite3.IntegrityError:
                pass
    conn.commit()
    return todo_id


def edit_todo(conn, todo_id, title=None, priority=None, due_date=None, note=None, tags=None):
    updates = []
    params = []
    if title is not None:
        updates.append("title = ?")
        params.append(title)
    if priority is not None:
        updates.append("priority = ?")
        params.append(priority)
    if due_date is not None:
        updates.append("due_date = ?")
        params.append(normalize_date(due_date) if due_date != '' else None)
    if note is not None:
        updates.append("note = ?")
        params.append(note)
    if updates:
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(todo_id)
        conn.execute(f"UPDATE todos SET {', '.join(updates)} WHERE id = ?", params)
    if tags is not None:
        conn.execute("DELETE FROM todo_tags WHERE todo_id = ?", (todo_id,))
        for tag in tags:
            try:
                conn.execute("INSERT INTO todo_tags (todo_id, tag) VALUES (?, ?)", (todo_id, tag))
            except sqlite3.IntegrityError:
                pass
    conn.commit()


def mark_done(conn, todo_id):
    conn.execute("UPDATE todos SET status = 'done', completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                 (todo_id,))
    conn.commit()


def delete_todo(conn, todo_id):
    conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
    conn.commit()


def get_todo(conn, todo_id):
    return conn.execute("SELECT * FROM todos WHERE id = ?", (todo_id,)).fetchone()


def get_todo_tags(conn, todo_id):
    rows = conn.execute("SELECT tag FROM todo_tags WHERE todo_id = ?", (todo_id,)).fetchall()
    return [r['tag'] for r in rows]


def list_todos(conn, status=None, tag=None, priority=None, due_date=None, limit=50):
    sql = "SELECT DISTINCT t.* FROM todos t"
    joins = []
    where = []
    params = []
    if tag:
        joins.append(" JOIN todo_tags tt ON t.id = tt.todo_id")
        where.append("tt.tag = ?")
        params.append(tag)
    sql += ''.join(joins)
    if status:
        where.append("t.status = ?")
        params.append(status)
    if priority:
        where.append("t.priority = ?")
        params.append(priority)
    if due_date:
        where.append("t.due_date <= ?")
        params.append(due_date)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY t.id ASC LIMIT ?"
    params.append(limit)
    return conn.execute(sql, params).fetchall()


def list_due_within(conn, days):
    today = date.today().strftime('%Y-%m-%d')
    end = (date.today() + timedelta(days=days)).strftime('%Y-%m-%d')
    return conn.execute(
        "SELECT * FROM todos WHERE status = 'pending' AND due_date IS NOT NULL AND due_date >= ? AND due_date <= ? ORDER BY due_date ASC",
        (today, end)).fetchall()


def list_all_tags(conn):
    return conn.execute("SELECT tag, COUNT(*) as count FROM todo_tags GROUP BY tag ORDER BY count DESC").fetchall()
