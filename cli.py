#!/usr/bin/env python3
"""TodoTool CLI — HurricaneSoft 待辦事項管理工具。"""
import argparse
import sys
import os
import getpass

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from todotool import db
from todotool import __version__


SESSION_USER = None

PRIORITY_ICON = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}
STATUS_ICON = {'pending': '📝', 'done': '✅'}


def require_auth(conn, args=None):
    """Check if any user exists, if so require login. Supports LIDS."""
    global SESSION_USER
    if SESSION_USER:
        return True

    # Try LIDS auth first
    try:
        from hurricanesoft_auth.wrapper import try_lids_auth
        lids_user = try_lids_auth(args)
        if lids_user:
            SESSION_USER = lids_user
            return True
    except ImportError:
        pass

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


def build_parser():
    # Missing child options must not overwrite values parsed before the command.
    common = argparse.ArgumentParser(add_help=False, argument_default=argparse.SUPPRESS)
    common.add_argument('--user', help='登入帳號')
    common.add_argument('--password', help='登入密碼')
    common.add_argument('--lids', action='store_true', help='使用 LIDS 認證')

    parser = argparse.ArgumentParser(prog='todotool', description='HurricaneSoft 待辦事項管理工具')
    parser.add_argument('--version', action='version', version=f'todotool v{__version__}')
    parser.add_argument('--user', help='登入帳號')
    parser.add_argument('--password', help='登入密碼')
    parser.add_argument('--lids', action='store_true', help='使用 LIDS 認證')

    sub = parser.add_subparsers(dest='command')

    # init
    p = sub.add_parser('init', help='初始化資料庫', parents=[common])
    p.add_argument('--admin-user', help='管理員帳號')
    p.add_argument('--admin-password', help='管理員密碼')

    # add
    p = sub.add_parser('add', help='新增待辦事項', parents=[common])
    p.add_argument('title', help='標題')
    p.add_argument('--priority', choices=['high', 'medium', 'low'], default='medium', help='優先度')
    p.add_argument('--due', help='到期日 (YYYY-MM-DD)')
    p.add_argument('--note', help='備註')
    p.add_argument('--tag', action='append', help='標籤（可多次使用）')

    # list
    p = sub.add_parser('list', help='列出待辦事項', parents=[common])
    p.add_argument('--status', choices=['pending', 'done'], help='狀態篩選')
    p.add_argument('--tag', help='標籤篩選')
    p.add_argument('--priority', choices=['high', 'medium', 'low'], help='優先度篩選')
    p.add_argument('--due', help='到期日前 (YYYY-MM-DD)')
    p.add_argument('--limit', type=int, default=50)

    # done
    p = sub.add_parser('done', help='標記完成', parents=[common])
    p.add_argument('id', type=int, help='待辦事項 ID')

    # edit
    p = sub.add_parser('edit', help='編輯待辦事項', parents=[common])
    p.add_argument('id', type=int, help='待辦事項 ID')
    p.add_argument('--title', help='新標題')
    p.add_argument('--priority', choices=['high', 'medium', 'low'], help='新優先度')
    p.add_argument('--due', help='新到期日 (YYYY-MM-DD)')
    p.add_argument('--note', help='新備註')
    p.add_argument('--tag', action='append', help='新標籤（可多次使用，取代現有標籤）')

    # history
    p = sub.add_parser('history', help='查看修改紀錄', parents=[common])
    p.add_argument('id', type=int, help='待辦事項 ID')

    # due
    p = sub.add_parser('due', help='查詢即將到期事項', parents=[common])
    p.add_argument('--days', type=int, default=7, help='天數（預設 7）')

    # tag
    p = sub.add_parser('tag', help='標籤管理', parents=[common])
    p.add_argument('action', choices=['list'], help='動作')

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
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
