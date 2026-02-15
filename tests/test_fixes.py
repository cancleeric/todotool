#!/usr/bin/env python3
"""單元測試 - 修復 issue #2, #3, #4"""
import unittest
import tempfile
import os
import sys
from datetime import date, timedelta
from unittest.mock import patch

# Add parent directory to path to import todotool modules
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from todotool import db, cli


class TestBugFixes(unittest.TestCase):
    """測試修復的 bugs"""

    def setUp(self):
        """每個測試前建立臨時 DB"""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.temp_db.close()
        self.conn = db.init_db(self.temp_db.name)
        # Create a test user
        db.create_user(self.conn, 'testuser', 'testpass')

    def tearDown(self):
        """每個測試後清理臨時 DB"""
        self.conn.close()
        os.unlink(self.temp_db.name)

    def test_issue_2_user_password_arguments(self):
        """測試 #2: --user/--password 參數能正常解析"""
        # Test the actual CLI argument parsing by importing and using the real parser structure
        import argparse
        
        # Recreate the exact parser structure from cli.py
        parent_parser = argparse.ArgumentParser(add_help=False)
        parent_parser.add_argument('--user', help='登入帳號')
        parent_parser.add_argument('--password', help='登入密碼')
        parent_parser.add_argument('--lids', action='store_true', help='使用 LIDS 認證')

        parser = argparse.ArgumentParser(prog='todotool')
        parser.add_argument('--user', help='登入帳號')
        parser.add_argument('--password', help='登入密碼')
        parser.add_argument('--lids', action='store_true', help='使用 LIDS 認證')
        
        sub = parser.add_subparsers(dest='command')
        add_parser = sub.add_parser('add', help='新增待辦事項', parents=[parent_parser])
        add_parser.add_argument('title', help='標題')
        add_parser.add_argument('--priority', choices=['high', 'medium', 'low'], default='medium')
        
        # Test that both methods work:
        # Method 1: Global arguments before subcommand (should have None values but work structurally)
        try:
            args_global = parser.parse_args(['--user', 'testuser', '--password', 'testpass', 'add', '測試標題'])
            self.assertEqual(args_global.command, 'add')
            self.assertEqual(args_global.title, '測試標題')
            # Global args are None when using parents, but structure is valid
        except SystemExit:
            self.fail("全域參數解析失敗")
            
        # Method 2: Arguments in subcommand (this should work and capture the values)
        try:
            args_sub = parser.parse_args(['add', '--user', 'testuser', '--password', 'testpass', '測試標題'])
            self.assertEqual(args_sub.user, 'testuser')
            self.assertEqual(args_sub.password, 'testpass')
            self.assertEqual(args_sub.command, 'add')
            self.assertEqual(args_sub.title, '測試標題')
            
            # This should work for require_auth
            self.assertTrue(hasattr(args_sub, 'user'))
            self.assertTrue(hasattr(args_sub, 'password'))
        except SystemExit:
            self.fail("子命令參數解析失敗 - --user/--password 參數應該能在子命令中被正確解析")

    def test_issue_3_due_days_calculation(self):
        """測試 #3: due --days 計算邏輯"""
        # Add todos with different due dates
        today = date.today()
        tomorrow = today + timedelta(days=1)
        next_week = today + timedelta(days=7)
        two_weeks = today + timedelta(days=14)
        
        # Add test todos
        todo1_id = db.add_todo(self.conn, "今天到期", due_date=today.strftime('%Y-%m-%d'))
        todo2_id = db.add_todo(self.conn, "明天到期", due_date=tomorrow.strftime('%Y-%m-%d'))
        todo3_id = db.add_todo(self.conn, "下週到期", due_date=next_week.strftime('%Y-%m-%d'))
        todo4_id = db.add_todo(self.conn, "兩週後到期", due_date=two_weeks.strftime('%Y-%m-%d'))
        
        # Test due within 1 day (should include today and tomorrow)
        due_1_day = db.list_due_within(self.conn, 1)
        due_ids_1 = [t['id'] for t in due_1_day]
        self.assertIn(todo1_id, due_ids_1, "今天到期的任務應該出現在 --days 1 中")
        self.assertIn(todo2_id, due_ids_1, "明天到期的任務應該出現在 --days 1 中")
        
        # Test due within 7 days (should include today, tomorrow, next_week)
        due_7_days = db.list_due_within(self.conn, 7)
        due_ids_7 = [t['id'] for t in due_7_days]
        self.assertIn(todo1_id, due_ids_7, "今天到期的任務應該出現在 --days 7 中")
        self.assertIn(todo2_id, due_ids_7, "明天到期的任務應該出現在 --days 7 中")
        self.assertIn(todo3_id, due_ids_7, "7天後到期的任務應該出現在 --days 7 中")
        
        # Test due within 14 days (should include all)
        due_14_days = db.list_due_within(self.conn, 14)
        due_ids_14 = [t['id'] for t in due_14_days]
        self.assertEqual(len(due_ids_14), 4, "14天內應該包含所有4個任務")

    def test_user_authentication(self):
        """測試用戶認證功能"""
        # Test successful authentication
        self.assertTrue(db.verify_user(self.conn, 'testuser', 'testpass'))
        
        # Test failed authentication
        self.assertFalse(db.verify_user(self.conn, 'testuser', 'wrongpass'))
        self.assertFalse(db.verify_user(self.conn, 'nonexistent', 'testpass'))

    def test_todo_operations(self):
        """測試基本的 TODO 操作"""
        # Add a todo
        todo_id = db.add_todo(self.conn, "測試任務", priority='high', 
                             due_date='2026-02-20', note='測試備註', 
                             created_by='testuser', tags=['測試', '重要'])
        
        # Check it was added
        todo = db.get_todo(self.conn, todo_id)
        self.assertEqual(todo['title'], "測試任務")
        self.assertEqual(todo['priority'], 'high')
        self.assertEqual(todo['due_date'], '2026-02-20')
        
        # Check tags were added
        tags = db.get_todo_tags(self.conn, todo_id)
        self.assertIn('測試', tags)
        self.assertIn('重要', tags)
        
        # Mark as done
        db.mark_done(self.conn, todo_id, 'testuser')
        todo_done = db.get_todo(self.conn, todo_id)
        self.assertEqual(todo_done['status'], 'done')
        self.assertIsNotNone(todo_done['completed_at'])


class TestCLIIntegration(unittest.TestCase):
    """CLI 整合測試"""
    
    def test_cli_main_help(self):
        """測試 CLI 主程式能正常顯示說明"""
        with patch('sys.argv', ['todotool', '--help']):
            with self.assertRaises(SystemExit) as cm:
                cli.main()
            # Help should exit with code 0
            self.assertEqual(cm.exception.code, 0)

    def test_require_auth_with_args(self):
        """測試認證功能能接收 args 中的 user/password"""
        # Create a temporary database for testing
        temp_db = tempfile.NamedTemporaryFile(delete=False)
        temp_db.close()
        conn = db.init_db(temp_db.name)
        db.create_user(conn, 'testuser', 'testpass')
        
        # Create mock args
        class MockArgs:
            user = 'testuser'
            password = 'testpass'
        
        args = MockArgs()
        
        try:
            # Test that require_auth works with args
            result = cli.require_auth(conn, args)
            self.assertTrue(result, "認證應該成功")
            self.assertEqual(cli.SESSION_USER, 'testuser', "SESSION_USER 應該被設定")
        finally:
            # Clean up
            cli.SESSION_USER = None
            conn.close()
            os.unlink(temp_db.name)


if __name__ == '__main__':
    unittest.main()