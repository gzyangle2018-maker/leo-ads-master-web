"""
Leo Ads Master - Database Module
SQLite-based user management, permissions, and report storage.
"""
import sqlite3
import hashlib
import secrets
import os
import sys
from datetime import datetime
from typing import List, Dict, Optional, Tuple


def get_app_dir() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Database:
    def __init__(self, db_path: str = None):
        if db_path is None:
            base_dir = get_app_dir()
            db_path = os.path.join(base_dir, 'data', 'leo_ads_master.db')
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self.init_tables()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def init_tables(self):
        conn = self._connect()
        cursor = conn.cursor()

        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'member',
                display_name TEXT,
                created_at TEXT NOT NULL,
                is_active INTEGER DEFAULT 1
            )
        ''')

        # Reports table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                asin TEXT,
                report_type TEXT NOT NULL,
                data_summary TEXT,
                result_json TEXT,
                excel_path TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')

        # System config
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_config (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT
            )
        ''')

        # User LLM config (admin can assign APIs to team members)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_llm_configs (
                user_id INTEGER PRIMARY KEY,
                provider TEXT DEFAULT '',
                api_key TEXT DEFAULT '',
                base_url TEXT DEFAULT '',
                model TEXT DEFAULT '',
                use_team_shared INTEGER DEFAULT 1,
                updated_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')

        # Create default admin if not exists
        cursor.execute("SELECT id FROM users WHERE role='admin' LIMIT 1")
        if not cursor.fetchone():
            self._create_default_admin(cursor)

        conn.commit()
        conn.close()

    def _hash_password(self, password: str, salt: str = None) -> Tuple[str, str]:
        if salt is None:
            salt = secrets.token_hex(16)
        hash_value = hashlib.sha256((password + salt).encode()).hexdigest()
        return hash_value, salt

    def _create_default_admin(self, cursor):
        default_password = 'leo0417'
        password_hash, salt = self._hash_password(default_password)
        now = datetime.now().isoformat()
        cursor.execute('''
            INSERT INTO users (username, password_hash, salt, role, display_name, created_at, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', ('yangle', password_hash, salt, 'admin', '管理员', now, 1))

    def authenticate(self, username: str, password: str) -> Optional[Dict]:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, username, password_hash, salt, role, display_name, is_active FROM users WHERE username=?",
            (username,)
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None
        user_id, db_username, db_hash, salt, role, display_name, is_active = row
        if not is_active:
            return None

        password_hash, _ = self._hash_password(password, salt)
        if password_hash == db_hash:
            return {
                'id': user_id,
                'username': db_username,
                'role': role,
                'display_name': display_name
            }
        return None

    def create_user(self, username: str, password: str, role: str = 'member',
                    display_name: str = None, creator_role: str = 'member') -> Tuple[bool, str]:
        if creator_role != 'admin':
            return False, '只有管理员可以创建用户'

        if role not in ('admin', 'member'):
            return False, '角色必须是 admin 或 member'

        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE username=?", (username,))
        if cursor.fetchone():
            conn.close()
            return False, '用户名已存在'

        password_hash, salt = self._hash_password(password)
        now = datetime.now().isoformat()
        display = display_name or username
        cursor.execute('''
            INSERT INTO users (username, password_hash, salt, role, display_name, created_at, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (username, password_hash, salt, role, display, now, 1))
        conn.commit()
        conn.close()
        return True, '用户创建成功'

    def delete_user(self, user_id: int, actor_role: str = 'member') -> Tuple[bool, str]:
        if actor_role != 'admin':
            return False, '只有管理员可以删除用户'

        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute("SELECT role FROM users WHERE id=?", (user_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False, '用户不存在'
        if row[0] == 'admin':
            # Prevent deleting the last admin
            cursor.execute("SELECT COUNT(*) FROM users WHERE role='admin'")
            if cursor.fetchone()[0] <= 1:
                conn.close()
                return False, '不能删除最后一个管理员'

        cursor.execute("UPDATE users SET is_active=0 WHERE id=?", (user_id,))
        conn.commit()
        conn.close()
        return True, '用户已停用'

    def reset_password(self, user_id: int, new_password: str, actor_role: str = 'member') -> Tuple[bool, str]:
        if actor_role != 'admin':
            return False, '只有管理员可以重置密码'

        conn = self._connect()
        cursor = conn.cursor()
        password_hash, salt = self._hash_password(new_password)
        cursor.execute(
            "UPDATE users SET password_hash=?, salt=? WHERE id=?",
            (password_hash, salt, user_id)
        )
        conn.commit()
        conn.close()
        return True, '密码重置成功'

    def list_users(self, actor_role: str = 'member') -> List[Dict]:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, username, role, display_name, created_at, is_active FROM users ORDER BY id"
        )
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                'id': r[0], 'username': r[1], 'role': r[2],
                'display_name': r[3], 'created_at': r[4], 'is_active': r[5]
            }
            for r in rows
        ]

    def save_report(self, user_id: int, title: str, report_type: str,
                    asin: str = None, data_summary: str = None,
                    result_json: str = None, excel_path: str = None) -> int:
        conn = self._connect()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute('''
            INSERT INTO reports (user_id, title, asin, report_type, data_summary, result_json, excel_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, title, asin, report_type, data_summary, result_json, excel_path, now))
        report_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return report_id

    def get_reports(self, user_id: int = None, role: str = 'member') -> List[Dict]:
        conn = self._connect()
        cursor = conn.cursor()
        if role == 'admin':
            cursor.execute('''
                SELECT r.id, r.title, r.asin, r.report_type, r.created_at, r.excel_path,
                       u.username, u.display_name
                FROM reports r JOIN users u ON r.user_id = u.id
                ORDER BY r.created_at DESC
            ''')
        else:
            cursor.execute('''
                SELECT r.id, r.title, r.asin, r.report_type, r.created_at, r.excel_path,
                       u.username, u.display_name
                FROM reports r JOIN users u ON r.user_id = u.id
                WHERE r.user_id = ?
                ORDER BY r.created_at DESC
            ''', (user_id,))
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                'id': r[0], 'title': r[1], 'asin': r[2], 'report_type': r[3],
                'created_at': r[4], 'excel_path': r[5],
                'username': r[6], 'display_name': r[7]
            }
            for r in rows
        ]

    def get_report_by_id(self, report_id: int) -> Optional[Dict]:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, user_id, title, asin, report_type, data_summary, result_json, excel_path, created_at FROM reports WHERE id=?",
            (report_id,)
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return {
            'id': row[0], 'user_id': row[1], 'title': row[2], 'asin': row[3],
            'report_type': row[4], 'data_summary': row[5],
            'result_json': row[6], 'excel_path': row[7], 'created_at': row[8]
        }

    def set_config(self, key: str, value: str):
        conn = self._connect()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute(
            "INSERT OR REPLACE INTO system_config (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, now)
        )
        conn.commit()
        conn.close()

    def get_config(self, key: str, default: str = '') -> str:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM system_config WHERE key=?", (key,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else default

    # --- User LLM Config ---
    def set_user_llm_config(self, user_id: int, provider: str = '', api_key: str = '',
                            base_url: str = '', model: str = '', use_team_shared: int = 1):
        conn = self._connect()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute('''
            INSERT OR REPLACE INTO user_llm_configs
            (user_id, provider, api_key, base_url, model, use_team_shared, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, provider, api_key, base_url, model, use_team_shared, now))
        conn.commit()
        conn.close()

    def get_user_llm_config(self, user_id: int) -> dict:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT provider, api_key, base_url, model, use_team_shared, updated_at
            FROM user_llm_configs WHERE user_id=?
        ''', (user_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return {
                'provider': '', 'api_key': '', 'base_url': '',
                'model': '', 'use_team_shared': 1, 'updated_at': ''
            }
        return {
            'provider': row[0], 'api_key': row[1], 'base_url': row[2],
            'model': row[3], 'use_team_shared': row[4], 'updated_at': row[5]
        }

    def list_user_llm_configs(self) -> List[Dict]:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT u.id, u.username, u.display_name, u.role,
                   c.provider, c.api_key, c.base_url, c.model, c.use_team_shared
            FROM users u LEFT JOIN user_llm_configs c ON u.id = c.user_id
            WHERE u.is_active = 1 ORDER BY u.id
        ''')
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                'id': r[0], 'username': r[1], 'display_name': r[2], 'role': r[3],
                'provider': r[4] or '', 'api_key': (r[5][:6] + '****') if r[5] else '',
                'base_url': r[6] or '', 'model': r[7] or '',
                'use_team_shared': r[8] if r[8] is not None else 1
            }
            for r in rows
        ]
