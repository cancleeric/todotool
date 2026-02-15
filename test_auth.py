#!/usr/bin/env python3
"""Unit tests for TodoTool authentication."""
import unittest
import tempfile
import os
import sqlite3
import json
from unittest.mock import patch, MagicMock
from io import StringIO
import sys

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(__file__))
import db
from cli import verify_lids_token, require_auth


class MockArgs:
    """Mock args object for testing."""
    def __init__(self, **kwargs):
        self.auth_mode = kwargs.get('auth_mode', 'local')
        self.user = kwargs.get('user', None)
        self.password = kwargs.get('password', None)
        self.token = kwargs.get('token', None)


class TestLocalAuth(unittest.TestCase):
    """Test local authentication."""
    
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.temp_db.close()
        self.conn = db.init_db(self.temp_db.name)
        # Clear session user for each test
        import cli
        cli.SESSION_USER = None
        
    def tearDown(self):
        self.conn.close()
        os.unlink(self.temp_db.name)
        # Clear session user
        import cli
        cli.SESSION_USER = None
        
    def test_no_users_allows_access(self):
        """Test that access is allowed when no users exist."""
        args = MockArgs(auth_mode='local')
        result = require_auth(self.conn, args)
        self.assertTrue(result)
        
    def test_valid_user_password(self):
        """Test authentication with valid user/password."""
        # Create a test user
        db.create_user(self.conn, 'testuser', 'testpass')
        
        args = MockArgs(auth_mode='local', user='testuser', password='testpass')
        result = require_auth(self.conn, args)
        self.assertTrue(result)
        
    def test_invalid_user_password(self):
        """Test authentication with invalid user/password."""
        # Create a test user
        db.create_user(self.conn, 'testuser', 'testpass')
        
        args = MockArgs(auth_mode='local', user='testuser', password='wrongpass')
        result = require_auth(self.conn, args)
        self.assertFalse(result)
        
    def test_nonexistent_user(self):
        """Test authentication with non-existent user."""
        # Create a test user
        db.create_user(self.conn, 'testuser', 'testpass')
        
        args = MockArgs(auth_mode='local', user='nonexistent', password='testpass')
        result = require_auth(self.conn, args)
        self.assertFalse(result)


class TestLIDSAuth(unittest.TestCase):
    """Test LIDS authentication."""
    
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.temp_db.close()
        self.conn = db.init_db(self.temp_db.name)
        # Clear session user for each test
        import cli
        cli.SESSION_USER = None
        
    def tearDown(self):
        self.conn.close()
        os.unlink(self.temp_db.name)
        # Clear session user
        import cli
        cli.SESSION_USER = None
        
    def test_missing_lids_url(self):
        """Test LIDS auth when LIDS_API_URL is not set."""
        with patch.dict(os.environ, {}, clear=True):
            result = verify_lids_token('valid_token')
            self.assertIsNone(result)
            
    @patch('urllib.request.urlopen')
    def test_valid_lids_token(self, mock_urlopen):
        """Test LIDS auth with valid token."""
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            'valid': True,
            'username': 'lids_user'
        }).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        with patch.dict(os.environ, {'LIDS_API_URL': 'http://lids.example.com'}):
            result = verify_lids_token('valid_token')
            self.assertEqual(result, 'lids_user')
            
    @patch('urllib.request.urlopen')
    def test_invalid_lids_token(self, mock_urlopen):
        """Test LIDS auth with invalid token."""
        # Mock failed API response
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            'valid': False
        }).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        with patch.dict(os.environ, {'LIDS_API_URL': 'http://lids.example.com'}):
            result = verify_lids_token('invalid_token')
            self.assertIsNone(result)
            
    @patch('urllib.request.urlopen')
    def test_lids_api_error(self, mock_urlopen):
        """Test LIDS auth when API call fails."""
        mock_urlopen.side_effect = Exception('Network error')
        
        with patch.dict(os.environ, {'LIDS_API_URL': 'http://lids.example.com'}):
            result = verify_lids_token('any_token')
            self.assertIsNone(result)
            
    @patch.dict(os.environ, {'LIDS_API_URL': 'http://lids.example.com'})
    @patch('urllib.request.urlopen')
    def test_lids_auth_mode_success(self, mock_urlopen):
        """Test require_auth with LIDS mode and valid token."""
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            'valid': True,
            'username': 'lids_user'
        }).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        args = MockArgs(auth_mode='lids', token='valid_token')
        result = require_auth(self.conn, args)
        self.assertTrue(result)
        
    @patch.dict(os.environ, {'LIDS_API_URL': 'http://lids.example.com'})
    @patch('urllib.request.urlopen')
    def test_lids_auth_mode_failure(self, mock_urlopen):
        """Test require_auth with LIDS mode and invalid token."""
        # Mock failed API response
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            'valid': False
        }).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        args = MockArgs(auth_mode='lids', token='invalid_token')
        result = require_auth(self.conn, args)
        self.assertFalse(result)


class TestAuthIntegration(unittest.TestCase):
    """Integration tests for authentication modes."""
    
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.temp_db.close()
        self.conn = db.init_db(self.temp_db.name)
        # Clear session user for each test
        import cli
        cli.SESSION_USER = None
        
    def tearDown(self):
        self.conn.close()
        os.unlink(self.temp_db.name)
        # Clear session user
        import cli
        cli.SESSION_USER = None
        
    def test_default_auth_mode_is_local(self):
        """Test that default auth mode is local."""
        args = MockArgs()  # No auth_mode specified
        self.assertEqual(args.auth_mode, 'local')
        
    @patch.dict(os.environ, {'LIDS_API_URL': 'http://lids.example.com'})
    @patch('urllib.request.urlopen')
    def test_lids_mode_ignores_local_credentials(self, mock_urlopen):
        """Test that LIDS mode ignores local user/password."""
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            'valid': True,
            'username': 'lids_user'
        }).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        # Create a local user but use LIDS mode
        db.create_user(self.conn, 'localuser', 'localpass')
        
        args = MockArgs(auth_mode='lids', token='lids_token', 
                       user='localuser', password='localpass')
        result = require_auth(self.conn, args)
        self.assertTrue(result)
        
    def test_local_mode_ignores_lids_token(self):
        """Test that local mode ignores LIDS token."""
        # Create a local user
        db.create_user(self.conn, 'localuser', 'localpass')
        
        args = MockArgs(auth_mode='local', user='localuser', password='localpass', 
                       token='unused_lids_token')
        result = require_auth(self.conn, args)
        self.assertTrue(result)


if __name__ == '__main__':
    unittest.main()