# services/journal/intel/auth.py
"""Authentication middleware for the Journal service.

Validates app session JWTs (issued by SSE after WordPress SSO) and resolves
user_id from the shared users table.

The app session JWT has this structure:
{
    "iat": 1234567890,
    "exp": 1234567890,
    "wp": {
        "issuer": "fotw" or "0-dte",
        "id": "wp_user_id",
        "email": "user@example.com",
        "name": "Display Name",
        "roles": ["subscriber"]
    }
}
"""

import jwt
import json
from typing import Optional, Dict, Any
from functools import wraps
from aiohttp import web


class JournalAuth:
    """Handles JWT validation and user resolution for the journal service."""

    def __init__(self, config: Dict[str, Any], db_pool):
        """
        Initialize auth handler.

        Args:
            config: Service config containing APP_SESSION_SECRET
            db_pool: MySQL connection pool for user lookups
        """
        # App session secret (same as SSE uses to sign session JWTs)
        self.app_session_secret = config.get('APP_SESSION_SECRET', '')
        self._pool = db_pool

    def _get_conn(self):
        """Get a database connection from the pool."""
        return self._pool.get_connection()

    def decode_app_session(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Decode and validate an app session JWT.

        Args:
            token: The JWT token string (from ms_session cookie or Authorization header)

        Returns:
            Decoded payload or None if invalid
        """
        if not token or not self.app_session_secret:
            return None

        try:
            payload = jwt.decode(
                token,
                self.app_session_secret,
                algorithms=['HS256']
            )
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    def get_user_from_session(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Decode app session token and fetch user from database.

        Args:
            token: App session JWT string

        Returns:
            User dict with id, email, etc. or None
        """
        payload = self.decode_app_session(token)
        if not payload:
            return None

        # Extract WP user info from session
        wp = payload.get('wp', {})
        issuer = (wp.get('issuer') or '').strip()
        wp_user_id = str(wp.get('id') or '').strip()

        if not issuer or not wp_user_id:
            return None

        # Look up user in database
        user = self.get_user_by_wp_id(issuer, wp_user_id)
        if user:
            return user

        # User not found - they may not have been persisted yet
        # Return session data without db user (id will be None)
        return {
            'id': None,
            'issuer': issuer,
            'wp_user_id': wp_user_id,
            'email': wp.get('email'),
            'display_name': wp.get('name'),
            'roles': wp.get('roles', []),
            'is_admin': 'administrator' in (wp.get('roles') or []),
            'subscription_tier': None,
        }

    def get_user_by_wp_id(self, issuer: str, wp_user_id: str) -> Optional[Dict[str, Any]]:
        """
        Look up user by issuer and WordPress user ID.

        Args:
            issuer: The issuer (e.g., 'fotw' or '0-dte')
            wp_user_id: WordPress user ID

        Returns:
            User dict or None
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM users WHERE issuer = %s AND wp_user_id = %s",
                (issuer, wp_user_id)
            )
            row = cursor.fetchone()
            if not row:
                return None

            columns = [col[0] for col in cursor.description]
            user = dict(zip(columns, row))

            return {
                'id': user['id'],
                'issuer': user['issuer'],
                'wp_user_id': user['wp_user_id'],
                'email': user.get('email'),
                'display_name': user.get('display_name'),
                'roles': json.loads(user.get('roles_json') or '[]'),
                'is_admin': bool(user.get('is_admin')),
                'subscription_tier': user.get('subscription_tier'),
            }
        except Exception as e:
            print(f"[auth] Failed to get user: {e}")
            return None
        finally:
            cursor.close()
            conn.close()

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Look up user by internal ID.

        Args:
            user_id: Internal user ID

        Returns:
            User dict or None
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            row = cursor.fetchone()
            if not row:
                return None

            columns = [col[0] for col in cursor.description]
            user = dict(zip(columns, row))

            return {
                'id': user['id'],
                'issuer': user['issuer'],
                'wp_user_id': user['wp_user_id'],
                'email': user.get('email'),
                'display_name': user.get('display_name'),
                'roles': json.loads(user.get('roles_json') or '[]'),
                'is_admin': bool(user.get('is_admin')),
                'subscription_tier': user.get('subscription_tier'),
            }
        except Exception as e:
            print(f"[auth] Failed to get user by ID: {e}")
            return None
        finally:
            cursor.close()
            conn.close()

    def extract_token(self, request: web.Request) -> Optional[str]:
        """
        Extract app session token from request.

        Checks:
        1. Authorization header (Bearer token)
        2. ms_session cookie
        3. token query param

        Args:
            request: aiohttp request object

        Returns:
            Token string or None
        """
        # Check Authorization header
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            return auth_header[7:]

        # Check ms_session cookie
        cookies = request.cookies
        if 'ms_session' in cookies:
            return cookies['ms_session']

        # Check query param (for WebSocket connections)
        token = request.query.get('token')
        if token:
            return token

        return None

    def get_user_from_proxy_headers(self, request: web.Request) -> Optional[Dict[str, Any]]:
        """
        Get user from X-User-* headers (set by SSE gateway proxy).

        When SSE gateway proxies requests, it sets these headers after validating
        the session cookie. This allows the journal service to trust the identity.

        Args:
            request: aiohttp request object

        Returns:
            User dict or None
        """
        # Check for X-User headers from SSE gateway proxy
        x_user_id = request.headers.get('X-User-Id', '').strip()
        x_user_email = request.headers.get('X-User-Email', '').strip()
        x_user_issuer = request.headers.get('X-User-Issuer', '').strip()

        if not x_user_id or not x_user_issuer:
            return None

        # Look up user in database by WP credentials
        user = self.get_user_by_wp_id(x_user_issuer, x_user_id)
        if user:
            return user

        # User not found in DB yet - return basic info from headers
        # (user will be created on first full auth via SSE)
        return None

    async def get_request_user(self, request: web.Request) -> Optional[Dict[str, Any]]:
        """
        Get user from request.

        Trust model: JWT validation is handled by the SSE Gateway.
        Internal services trust the gateway's X-User-* headers.

        Checks in order:
        1. X-User-* headers (from SSE gateway proxy)
        2. X-Internal-User-Id header (internal service auth, localhost only)

        Args:
            request: aiohttp request object

        Returns:
            User dict or None
        """
        # Path 1: X-User headers from SSE gateway proxy (primary path)
        user = self.get_user_from_proxy_headers(request)
        if user and user.get('id'):
            return user

        # Path 2: Internal service auth (localhost only, uses internal DB user ID)
        # NOTE: Localhost-only auth is valid for single-node deployment.
        # Must be replaced with mTLS or service JWT in distributed/multi-node mode.
        x_internal_user = request.headers.get('X-Internal-User-Id', '').strip()
        if x_internal_user:
            # Reject ambiguous requests with both internal and proxy headers
            x_user_id = request.headers.get('X-User-Id', '').strip()
            if x_user_id:
                return None  # Ambiguous — refuse rather than guess
            peername = request.transport.get_extra_info('peername')
            if peername and peername[0] in ('127.0.0.1', '::1'):
                try:
                    user = self.get_user_by_id(int(x_internal_user))
                    if user:
                        return user
                except (ValueError, TypeError):
                    pass

        return None


def require_auth(handler):
    """
    Decorator to require authentication on a route handler.

    Adds request['user'] with the authenticated user.
    Returns 401 if not authenticated.
    """
    @wraps(handler)
    async def wrapper(self, request: web.Request) -> web.Response:
        user = await self.auth.get_request_user(request)
        if not user:
            return self._error_response('Authentication required', 401)

        # Attach user to request for handler to use
        request['user'] = user
        return await handler(self, request)

    return wrapper


def optional_auth(handler):
    """
    Decorator to optionally authenticate a route handler.

    Adds request['user'] with the authenticated user or None.
    Does not reject unauthenticated requests.
    """
    @wraps(handler)
    async def wrapper(self, request: web.Request) -> web.Response:
        user = await self.auth.get_request_user(request)
        request['user'] = user
        return await handler(self, request)

    return wrapper
