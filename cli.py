#!/usr/bin/env python3
"""TodoTool CLI — HurricaneSoft 待辦事項管理工具。"""
import argparse
import sys
import os
import getpass
import json
import urllib.request
import urllib.parse
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from todotool import db
from todotool import __version__


SESSION_USER = None

PRIORITY_ICON = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}
STATUS_ICON = {'pending': '📝', 'done': '✅'}


def verify_lids_token(token):
    """Verify token with LIDS API and return username if valid."""
    lids_url = os.environ.get('LIDS_API_URL', '')
    if not lids_url:
        print("❌ LIDS_API_URL 環境變數未設定")
        return None
    
    try:
        # 準備 API 請求
        url = f"{lids_url.rstrip('/')}/api/verify"
        data = json.dumps({'token': token}).encode('utf-8')
        req = urllib.request.Request(url, data=data)
        req.add_header('Content-Type', 'application/json')
        
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            if result.get('valid', False):
                return result.get('username', 'lids_user')
            else:
                return None
    except (urllib.error.URLError, json.JSONDecodeError, Exception) as e:
        print(f"❌ LIDS 驗證錯誤: {e}")
        return None


def require_auth(conn, args=None):
    """Check if any user exists, if so require login. Supports local and LIDS auth modes."""
    global SESSION_USER
    if SESSION_USER:
        return True

    auth_mode = getattr(args, 'auth_mode', 'local')
    
    if auth_mode == 'lids':
        # LIDS OAuth 認證模式
        token = getattr(args, 'token', None) or os.environ.get('LIDS_TOKEN', '')
        if not token:
            try:
                print("🔐 LIDS 認證")
                token = getpass.getpass("LIDS Token: ")
            except (EOFError, OSError):
                print("❌ 需要 LIDS token（用 --token 或環境變數 LIDS_TOKEN）")
                return False
        
        username = verify_lids_token(token)
        if username:
            SESSION_USER = username
            print(f"✅ LIDS 登入成功, {username}")
            return True
        else:
            print("❌ LIDS token 無效")
            return False
    
    else:
        # local 認證模式（原本的邏輯）
        username = getattr(args, 'user', None) or os.environ.get('TODO_USER', '')
        password = getattr(args, 'password', None) or os.environ.get('TODO_PASSWORD', '')
        users = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()['c']
        if users == 0:
            return True
        if username and password:
            if db.verify_user(conn, username, password):
                SESSION_USER = username
                return True
            print("❌ 帳號或密碼錯誤")
            return False
        try:
            print("🔐 請先登入")
            username = input("帳號: ")
            password = getpass.getpass("密碼: ")
        except (EOFError, OSError):
            print("❌ 需要帳號密碼（用 --user/--password 或環境變數 TODO_USER/TODO_PASSWORD）")
            return False
        if db.verify_user(conn, username, password):
            SESSION_USER = username
            print(f"✅ 歡迎, {username}")
            return True
        else:
            print("❌ 帳號或密碼錯誤")
            return False


def cmd_init(args):
    """Initialize database and create admin user."""
    conn = db.init_db()
    print("✅ 資料庫初始化完成")

    users = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()['c']
    if users == 0:
        username = getattr(args, 'admin_user', None)
        password = getattr(args, 'admin_password', None)
        if not username or not password:
            try:
                print("\n建立管理員帳號：")
                username = input("帳號: ")
                password = getpass.getpass("密碼: ")
                password2 = getpass.getpass("確認密碼: ")
                if password != password2:
                    print("❌ 密碼不一致")
                    return
            except (EOFError, OSError):
                print("❌ 用 --admin-user 和 --admin-password 建立管理員")
                return
        db.create_user(conn, username, password)
        print(f"✅ 管理員 '{username}' 建立完成")


def cmd_add(args):
    """Add a todo."""
    conn = db.init_db()
    if not require_auth(conn, args):
        return

    todo_id = db.add_todo(conn, args.title, priority=args.priority or 'medium',
                          due_date=args.due, note=args.note or '',
                          created_by=SESSION_USER or '', tags=args.tag)
    icon = PRIORITY_ICON.get(args.priority or 'medium', '🟡')
    due_str = f" 📅 {args.due}" if args.due else ""
    tag_str = f" 🏷️ {', '.join(args.tag)}" if args.tag else ""
    print(f"{icon} 已新增 [{todo_id}] {args.title}{due_str}{tag_str}")


def cmd_list(args):
    """List todos."""
    conn = db.init_db()
    if not require_auth(conn, args):
        return

    todos = db.list_todos(conn, status=args.status, tag=args.tag,
                          priority=args.priority, due_date=args.due, limit=args.limit)
    if not todos:
        print("📭 沒有待辦事項")
        return

    print(f"{'ID':>4} {'狀態':<4} {'優先':>4} {'標題':<20} {'到期日':<12} {'標籤'}")
    print('─' * 65)
    for t in todos:
        s_icon = STATUS_ICON.get(t['status'], '📝')
        p_icon = PRIORITY_ICON.get(t['priority'], '🟡')
        tags = db.get_todo_tags(conn, t['id'])
        tag_str = ', '.join(tags) if tags else ''
        due_str = t['due_date'] or ''
        print(f"{t['id']:>4} {s_icon}  {p_icon}  {t['title']:<20} {due_str:<12} {tag_str}")


def cmd_done(args):
    """Mark a todo as done."""
    conn = db.init_db()
    if not require_auth(conn, args):
        return

    todo = db.get_todo(conn, args.id)
    if not todo:
        print(f"❌ 找不到待辦事項 [{args.id}]")
        return
    db.mark_done(conn, args.id, changed_by=SESSION_USER or '')
    print(f"✅ [{args.id}] {todo['title']} — 已完成！")


def cmd_edit(args):
    """Edit a todo."""
    conn = db.init_db()
    if not require_auth(conn, args):
        return

    todo = db.get_todo(conn, args.id)
    if not todo:
        print(f"❌ 找不到待辦事項 [{args.id}]")
        return
    db.edit_todo(conn, args.id, title=args.title, priority=args.priority,
                 due_date=args.due, note=args.note, tags=args.tag, changed_by=SESSION_USER or '')
    print(f"📝 [{args.id}] 已更新")


def cmd_history(args):
    """Show edit history for a todo."""
    conn = db.init_db()
    if not require_auth(conn, args):
        return

    todo = db.get_todo(conn, args.id)
    if not todo:
        print(f"❌ 找不到待辦事項 [{args.id}]")
        return

    history = db.get_history(conn, args.id)
    if not history:
        print(f"📋 [{args.id}] {todo['title']} — 沒有修改紀錄")
        return

    print(f"📋 [{args.id}] {todo['title']} — 修改紀錄：")
    for h in history:
        by = f"  (by {h['changed_by']})" if h['changed_by'] else ''
        print(f"  {h['changed_at']}  {h['field']}: {h['old_value']} → {h['new_value']}{by}")


def cmd_due(args):
    """Show todos due within N days."""
    conn = db.init_db()
    if not require_auth(conn, args):
        return

    todos = db.list_due_within(conn, args.days)
    if not todos:
        print(f"📭 未來 {args.days} 天內沒有到期的待辦事項")
        return

    print(f"⏰ 未來 {args.days} 天內到期：")
    print(f"{'ID':>4} {'優先':>4} {'標題':<20} {'到期日':<12} {'標籤'}")
    print('─' * 55)
    for t in todos:
        p_icon = PRIORITY_ICON.get(t['priority'], '🟡')
        tags = db.get_todo_tags(conn, t['id'])
        tag_str = ', '.join(tags) if tags else ''
        print(f"{t['id']:>4} {p_icon}  {t['title']:<20} {t['due_date']:<12} {tag_str}")


def cmd_tag(args):
    """Manage tags."""
    conn = db.init_db()
    if not require_auth(conn, args):
        return

    if args.action == 'list':
        tags = db.list_all_tags(conn)
        if not tags:
            print("📭 沒有標籤")
            return
        print("🏷️ 所有標籤：")
        for t in tags:
            print(f"  {t['tag']} ({t['count']})")


def main():
    parser = argparse.ArgumentParser(prog='todotool', description='HurricaneSoft 待辦事項管理工具')
    parser.add_argument('--version', action='version', version=f'todotool v{__version__}')
    parser.add_argument('--auth-mode', choices=['local', 'lids'], default='local', 
                       help='認證模式：local (本地 SQLite) 或 lids (LIDS OAuth)')
    parser.add_argument('--user', help='登入帳號 (local 模式)')
    parser.add_argument('--password', help='登入密碼 (local 模式)')
    parser.add_argument('--token', help='LIDS token (lids 模式)')
    # 保留舊的 --lids 參數以向後相容
    parser.add_argument('--lids', action='store_true', help='使用 LIDS 認證（等同 --auth-mode lids）')

    sub = parser.add_subparsers(dest='command')

    # init
    p = sub.add_parser('init', help='初始化資料庫')
    p.add_argument('--admin-user', help='管理員帳號')
    p.add_argument('--admin-password', help='管理員密碼')

    # add
    p = sub.add_parser('add', help='新增待辦事項')
    p.add_argument('title', help='標題')
    p.add_argument('--priority', choices=['high', 'medium', 'low'], default='medium', help='優先度')
    p.add_argument('--due', help='到期日 (YYYY-MM-DD)')
    p.add_argument('--note', help='備註')
    p.add_argument('--tag', action='append', help='標籤（可多次使用）')

    # list
    p = sub.add_parser('list', help='列出待辦事項')
    p.add_argument('--status', choices=['pending', 'done'], help='狀態篩選')
    p.add_argument('--tag', help='標籤篩選')
    p.add_argument('--priority', choices=['high', 'medium', 'low'], help='優先度篩選')
    p.add_argument('--due', help='到期日前 (YYYY-MM-DD)')
    p.add_argument('--limit', type=int, default=50)

    # done
    p = sub.add_parser('done', help='標記完成')
    p.add_argument('id', type=int, help='待辦事項 ID')

    # edit
    p = sub.add_parser('edit', help='編輯待辦事項')
    p.add_argument('id', type=int, help='待辦事項 ID')
    p.add_argument('--title', help='新標題')
    p.add_argument('--priority', choices=['high', 'medium', 'low'], help='新優先度')
    p.add_argument('--due', help='新到期日 (YYYY-MM-DD)')
    p.add_argument('--note', help='新備註')
    p.add_argument('--tag', action='append', help='新標籤（可多次使用，取代現有標籤）')

    # history
    p = sub.add_parser('history', help='查看修改紀錄')
    p.add_argument('id', type=int, help='待辦事項 ID')

    # due
    p = sub.add_parser('due', help='查詢即將到期事項')
    p.add_argument('--days', type=int, default=7, help='天數（預設 7）')

    # tag
    p = sub.add_parser('tag', help='標籤管理')
    p.add_argument('action', choices=['list'], help='動作')

    args = parser.parse_args()
    
    # 向後相容：--lids 設定 auth_mode 為 lids
    if args.lids:
        args.auth_mode = 'lids'
    
    if not args.command:
        parser.print_help()
        return

    cmds = {
        'init': cmd_init, 'add': cmd_add, 'list': cmd_list,
        'done': cmd_done, 'edit': cmd_edit, 'history': cmd_history,
        'due': cmd_due, 'tag': cmd_tag,
    }
    cmds[args.command](args)


if __name__ == '__main__':
    main()
