# utils/decorators.py
from functools import wraps
from flask import session, redirect, url_for, abort
from models import User
from constants import UserRole


def login_required(f):
    """로그인이 필요한 페이지에 대한 데코레이터"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        
        # 세션의 사용자가 실제로 존재하는지 확인
        username = session.get('username')
        user = User.query.filter_by(username=username).first()
        if not user:
            session.pop('username', None)  # 유효하지 않은 세션 제거
            return redirect(url_for('login'))
            
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """관리자 권한이 필요한 페이지에 대한 데코레이터"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        username = session.get('username')
        if not username:
            return redirect(url_for('login'))
        
        user_info = User.query.filter_by(username=username).first()
        if not user_info:
            session.pop('username', None)  # 유효하지 않은 세션 제거
            return redirect(url_for('login'))
        
        # 역할 검증 강화 - 정확한 문자열 매칭
        user_roles = user_info.role.split(',')
        user_roles = [role.strip() for role in user_roles]  # 공백 제거
        
        if UserRole.TEAM_LEADER not in user_roles:
            abort(403)  # Forbidden
        
        return f(*args, **kwargs)
    return decorated_function


def approval_required(f):
    """결재 권한이 필요한 페이지에 대한 데코레이터"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        username = session.get('username')
        if not username:
            return redirect(url_for('login'))
        
        user_info = User.query.filter_by(username=username).first()
        if not user_info:
            session.pop('username', None)
            return redirect(url_for('login'))
        
        # 결재 권한 검증
        user_roles = user_info.role.split(',')
        user_roles = [role.strip() for role in user_roles]
        
        has_approval_permission = (
            UserRole.TEAM_LEADER in user_roles or 
            UserRole.PART_LEADER in user_roles
        )
        
        if not has_approval_permission:
            abort(403)
        
        return f(*args, **kwargs)
    return decorated_function


def role_required(*required_roles):
    """특정 역할이 필요한 페이지에 대한 데코레이터"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            username = session.get('username')
            if not username:
                return redirect(url_for('login'))
            
            user_info = User.query.filter_by(username=username).first()
            if not user_info:
                session.pop('username', None)
                return redirect(url_for('login'))
            
            user_roles = user_info.role.split(',')
            user_roles = [role.strip() for role in user_roles]
            
            # 필요한 역할 중 하나라도 가지고 있는지 확인
            has_required_role = any(role in user_roles for role in required_roles)
            
            if not has_required_role:
                abort(403)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator
