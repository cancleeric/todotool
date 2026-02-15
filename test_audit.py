#!/usr/bin/env python3
"""Unit tests for audit log functionality."""
import unittest
import os
import tempfile
import sqlite3
from datetime import datetime, timedelta

import sys
sys.path.insert(0, os.path.dirname(__file__))
import db


class TestAuditLog(unittest.TestCase):
    def setUp(self):
        """Set up test database."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.conn = db.init_db(self.temp_db.name)
        
        # Create test user
        db.create_user(self.conn, 'testuser', 'password123')
        
    def tearDown(self):
        """Clean up test database."""
        self.conn.close()
        os.unlink(self.temp_db.name)
        
    def test_add_todo_no_audit_log(self):
        """Test adding todo doesn't create audit log entries."""
        todo_id = db.add_todo(self.conn, "Test todo", created_by="testuser")
        history = db.get_history(self.conn, todo_id)
        self.assertEqual(len(history), 0)
        
    def test_edit_todo_creates_audit_log(self):
        """Test editing todo creates audit log entries."""
        # Add a todo
        todo_id = db.add_todo(self.conn, "Original Title", priority="low", created_by="testuser")
        
        # Edit the todo
        db.edit_todo(self.conn, todo_id, title="New Title", priority="high", changed_by="testuser")
        
        # Check audit log
        history = db.get_history(self.conn, todo_id)
        self.assertEqual(len(history), 2)
        
        # Check title change log
        title_log = next((h for h in history if h['action'] == 'edit_title'), None)
        self.assertIsNotNone(title_log)
        self.assertEqual(title_log['old_value'], "Original Title")
        self.assertEqual(title_log['new_value'], "New Title")
        self.assertEqual(title_log['user'], "testuser")
        
        # Check priority change log
        priority_log = next((h for h in history if h['action'] == 'edit_priority'), None)
        self.assertIsNotNone(priority_log)
        self.assertEqual(priority_log['old_value'], "low")
        self.assertEqual(priority_log['new_value'], "high")
        self.assertEqual(priority_log['user'], "testuser")
        
    def test_mark_done_creates_audit_log(self):
        """Test marking todo as done creates audit log entry."""
        # Add a todo
        todo_id = db.add_todo(self.conn, "Test todo", created_by="testuser")
        
        # Mark as done
        db.mark_done(self.conn, todo_id, changed_by="testuser")
        
        # Check audit log
        history = db.get_history(self.conn, todo_id)
        self.assertEqual(len(history), 1)
        
        log_entry = history[0]
        self.assertEqual(log_entry['action'], 'mark_done')
        self.assertEqual(log_entry['old_value'], 'pending')
        self.assertEqual(log_entry['new_value'], 'done')
        self.assertEqual(log_entry['user'], 'testuser')
        
    def test_edit_tags_creates_audit_log(self):
        """Test editing tags creates audit log entry."""
        # Add a todo with tags
        todo_id = db.add_todo(self.conn, "Test todo", tags=['work', 'urgent'], created_by="testuser")
        
        # Edit tags
        db.edit_todo(self.conn, todo_id, tags=['personal', 'low'], changed_by="testuser")
        
        # Check audit log
        history = db.get_history(self.conn, todo_id)
        self.assertEqual(len(history), 1)
        
        log_entry = history[0]
        self.assertEqual(log_entry['action'], 'edit_tags')
        self.assertEqual(log_entry['old_value'], 'urgent,work')  # sorted
        self.assertEqual(log_entry['new_value'], 'low,personal')  # sorted
        self.assertEqual(log_entry['user'], 'testuser')
        
    def test_edit_due_date_creates_audit_log(self):
        """Test editing due date creates audit log entry."""
        # Add a todo
        todo_id = db.add_todo(self.conn, "Test todo", due_date="2026-03-01", created_by="testuser")
        
        # Edit due date
        db.edit_todo(self.conn, todo_id, due_date="2026-04-01", changed_by="testuser")
        
        # Check audit log
        history = db.get_history(self.conn, todo_id)
        self.assertEqual(len(history), 1)
        
        log_entry = history[0]
        self.assertEqual(log_entry['action'], 'edit_due_date')
        self.assertEqual(log_entry['old_value'], '2026-03-01')
        self.assertEqual(log_entry['new_value'], '2026-04-01')
        self.assertEqual(log_entry['user'], 'testuser')
        
    def test_edit_note_creates_audit_log(self):
        """Test editing note creates audit log entry."""
        # Add a todo
        todo_id = db.add_todo(self.conn, "Test todo", note="Original note", created_by="testuser")
        
        # Edit note
        db.edit_todo(self.conn, todo_id, note="Updated note", changed_by="testuser")
        
        # Check audit log
        history = db.get_history(self.conn, todo_id)
        self.assertEqual(len(history), 1)
        
        log_entry = history[0]
        self.assertEqual(log_entry['action'], 'edit_note')
        self.assertEqual(log_entry['old_value'], 'Original note')
        self.assertEqual(log_entry['new_value'], 'Updated note')
        self.assertEqual(log_entry['user'], 'testuser')
        
    def test_no_change_no_audit_log(self):
        """Test that no changes don't create audit log entries."""
        # Add a todo
        todo_id = db.add_todo(self.conn, "Test todo", priority="medium", created_by="testuser")
        
        # "Edit" with same values
        db.edit_todo(self.conn, todo_id, title="Test todo", priority="medium", changed_by="testuser")
        
        # Check audit log (should be empty)
        history = db.get_history(self.conn, todo_id)
        self.assertEqual(len(history), 0)
        
    def test_audit_log_table_structure(self):
        """Test that audit_log table has correct structure."""
        cursor = self.conn.execute("PRAGMA table_info(audit_log)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        
        expected_columns = {
            'id': 'INTEGER',
            'todo_id': 'INTEGER',
            'action': 'TEXT',
            'old_value': 'TEXT',
            'new_value': 'TEXT',
            'user': 'TEXT',
            'timestamp': 'DATETIME'
        }
        
        for col_name, col_type in expected_columns.items():
            self.assertIn(col_name, columns)
            
    def test_audit_log_timestamp_format(self):
        """Test that audit log entries have valid timestamps."""
        # Add a todo and edit it
        todo_id = db.add_todo(self.conn, "Test todo", created_by="testuser")
        db.edit_todo(self.conn, todo_id, title="Updated title", changed_by="testuser")
        
        # Check timestamp format
        history = db.get_history(self.conn, todo_id)
        self.assertEqual(len(history), 1)
        
        timestamp_str = history[0]['timestamp']
        # Should be parseable as datetime
        try:
            datetime.fromisoformat(timestamp_str.replace(' ', 'T'))
        except ValueError:
            self.fail(f"Invalid timestamp format: {timestamp_str}")
            
    def test_multiple_edits_chronological_order(self):
        """Test that multiple edits are stored in chronological order."""
        # Add a todo
        todo_id = db.add_todo(self.conn, "Test todo", created_by="testuser")
        
        # Multiple edits
        db.edit_todo(self.conn, todo_id, title="First edit", changed_by="testuser")
        db.edit_todo(self.conn, todo_id, priority="high", changed_by="testuser")
        db.edit_todo(self.conn, todo_id, title="Second edit", changed_by="testuser")
        
        # Check chronological order
        history = db.get_history(self.conn, todo_id)
        self.assertEqual(len(history), 3)
        
        # Should be in timestamp order
        timestamps = [datetime.fromisoformat(h['timestamp'].replace(' ', 'T')) for h in history]
        self.assertEqual(timestamps, sorted(timestamps))
        
        # Check sequence of changes
        self.assertEqual(history[0]['action'], 'edit_title')
        self.assertEqual(history[0]['new_value'], 'First edit')
        self.assertEqual(history[1]['action'], 'edit_priority')
        self.assertEqual(history[1]['new_value'], 'high')
        self.assertEqual(history[2]['action'], 'edit_title')
        self.assertEqual(history[2]['new_value'], 'Second edit')


if __name__ == '__main__':
    unittest.main()