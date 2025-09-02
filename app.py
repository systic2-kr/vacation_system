# app.py
from flask import Flask, render_template, request, redirect, url_for, session, flash
from config import Config
from models import db, User, Vacation, Notification
from services.vacation_service import VacationService
from services.user_service import UserService
from services.notification_service import NotificationService
from services.auth_service import AuthService
from utils.decorators import login_required, admin_required, approval_required
from utils.init_data import init_default_users


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    db.init_app(app)
    
    with app.app_context():
        db.create_all()
        # 초기 사용자 데이터 생성
        init_default_users()
    
    return app


app = create_app()
vacation_service = VacationService()
user_service = UserService()
notification_service = NotificationService()
auth_service = AuthService()


# Authentication Routes
@app.route('/')
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        # 입력값 검증
        if not username or not password:
            flash("아이디와 비밀번호를 모두 입력해주세요.", "error")
            return redirect(url_for('login'))
        
        result = auth_service.authenticate_user(username, password)
        
        if result['success']:
            session['username'] = username
            session.permanent = True  # 세션 보안 강화
            
            if result['is_temp_password']:
                flash("임시 비밀번호로 로그인하셨습니다. 새 비밀번호를 설정해주세요.", "warning")
                return redirect(url_for('change_password'))
            return redirect(url_for('dashboard'))
        else:
            flash(result['message'], "error")
            return redirect(url_for('login'))
    
    return render_template('login.html')


@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    username = session.get('username')
    
    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # 입력값 검증
        if not new_password or not confirm_password:
            flash("모든 필드를 입력해주세요.", "error")
            return redirect(url_for('change_password'))
        
        result = auth_service.change_password(username, new_password, confirm_password)
        flash(result['message'], result['type'])
        
        if result['success']:
            return redirect(url_for('dashboard'))
        
        return redirect(url_for('change_password'))

    return render_template('change_password.html')


@app.route('/logout')
def logout():
    session.clear()  # 모든 세션 데이터 제거로 보안 강화
    flash("성공적으로 로그아웃되었습니다.", "info")
    return redirect(url_for('login'))


# Dashboard
@app.route('/dashboard')
@login_required
def dashboard():
    try:
        username = session['username']
        user_info = user_service.get_user_by_username(username)
        
        if not user_info:
            session.clear()
            flash("사용자 정보를 찾을 수 없습니다.", "error")
            return redirect(url_for('login'))
        
        unread_count = notification_service.get_unread_count(user_info.id)
        user_roles = [role.strip() for role in user_info.role.split(',')]
        
        return render_template('dashboard.html', 
                               username=username, 
                               user_roles=user_roles, 
                               unread_notifications_count=unread_count)
    except Exception as e:
        flash("대시보드 로딩 중 오류가 발생했습니다.", "error")
        return redirect(url_for('login'))


# Vacation Routes
@app.route('/apply', methods=['GET', 'POST'])
@login_required
def apply_vacation():
    username = session['username']
    
    if request.method == 'POST':
        try:
            # 입력 데이터 검증 및 정제
            vacation_data = {
                'vacation_type': request.form.get('vacation_type', '').strip(),
                'start_date': request.form.get('start_date', '').strip(),
                'end_date': request.form.get('end_date', '').strip(),
                'reason': request.form.get('reason', '').strip(),
                'backup': request.form.get('backup', '').strip()
            }
            
            # 필수 필드 확인
            if not all(vacation_data.values()):
                flash("모든 필드를 입력해주세요.", "error")
                return redirect(url_for('apply_vacation'))
            
            result = vacation_service.apply_vacation(username, vacation_data)
            flash(result['message'], result['type'])
            
            if result['success']:
                return redirect(url_for('dashboard'))
            
        except Exception as e:
            flash("휴가 신청 처리 중 오류가 발생했습니다.", "error")
        
        return redirect(url_for('apply_vacation'))
    
    return render_template('apply.html')


@app.route('/history')
@login_required
def history():
    try:
        username = session['username']
        vacation_history = vacation_service.get_user_vacation_history(username)
        return render_template('history.html', history=vacation_history)
    except Exception as e:
        flash("휴가 내역 조회 중 오류가 발생했습니다.", "error")
        return redirect(url_for('dashboard'))


@app.route('/history/cancel/<int:vacation_id>', methods=['POST'])
@login_required
def cancel_vacation(vacation_id):
    try:
        username = session['username']
        result = vacation_service.cancel_vacation(vacation_id, username)
        flash(result['message'], result['type'])
    except Exception as e:
        flash("휴가 취소 처리 중 오류가 발생했습니다.", "error")
    
    return redirect(url_for('history'))


# Approval Routes
@app.route('/approvals')
@approval_required  # 새로운 데코레이터 사용
def approvals():
    try:
        username = session['username']
        approval_list = vacation_service.get_pending_approvals(username)
        return render_template('approvals.html', approval_list=approval_list)
    except Exception as e:
        flash("결재 목록 조회 중 오류가 발생했습니다.", "error")
        return redirect(url_for('dashboard'))


@app.route('/approvals/approve/<int:vacation_id>', methods=['POST'])
@approval_required
def approve_vacation(vacation_id):
    try:
        username = session['username']
        result = vacation_service.approve_vacation(vacation_id, username)
        flash(result['message'], result['type'])
    except Exception as e:
        flash("결재 승인 처리 중 오류가 발생했습니다.", "error")
    
    return redirect(url_for('approvals'))


@app.route('/approvals/reject/<int:vacation_id>', methods=['POST'])
@approval_required
def reject_vacation(vacation_id):
    try:
        username = session['username']
        result = vacation_service.reject_vacation(vacation_id, username)
        flash(result['message'], result['type'])
    except Exception as e:
        flash("결재 반려 처리 중 오류가 발생했습니다.", "error")
    
    return redirect(url_for('approvals'))


# Notification Routes
@app.route('/notifications')
@login_required
def notifications():
    try:
        username = session['username']
        user = user_service.get_user_by_username(username)
        
        if not user:
            session.clear()
            flash("사용자 정보를 찾을 수 없습니다.", "error")
            return redirect(url_for('login'))
        
        user_notifications = notification_service.get_user_notifications(user.id)
        notification_service.mark_all_as_read(user.id)
        
        return render_template('notifications.html', notifications=user_notifications)
    except Exception as e:
        flash("알림 조회 중 오류가 발생했습니다.", "error")
        return redirect(url_for('dashboard'))


# Admin Routes
@app.route('/admin')
@admin_required
def admin_dashboard():
    try:
        users = user_service.get_all_users()
        return render_template('admin_dashboard.html', users=users)
    except Exception as e:
        flash("관리자 페이지 로딩 중 오류가 발생했습니다.", "error")
        return redirect(url_for('dashboard'))


@app.route('/admin/add_user', methods=['GET', 'POST'])
@admin_required
def add_user():
    if request.method == 'POST':
        try:
            user_data = {
                'username': request.form.get('username', '').strip(),
                'join_date': request.form.get('join_date', '').strip(),
                'part': request.form.get('part', '').strip(),
                'role': request.form.get('role', '').strip()
            }
            
            # 필수 필드 확인
            if not all(user_data.values()):
                flash("모든 필드를 입력해주세요.", "error")
                return redirect(url_for('add_user'))
            
            result = user_service.create_user(user_data)
            flash(result['message'], result['type'])
            
            if result['success']:
                return redirect(url_for('admin_dashboard'))
                
        except Exception as e:
            flash("사용자 추가 처리 중 오류가 발생했습니다.", "error")

    return render_template('add_user.html')


@app.route('/admin/edit_user/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def edit_user(user_id):
    try:
        user = user_service.get_user_by_id(user_id)
        if not user:
            flash("사용자를 찾을 수 없습니다.", "error")
            return redirect(url_for('admin_dashboard'))
        
        if request.method == 'POST':
            user_data = {
                'username': request.form.get('username', '').strip(),
                'join_date': request.form.get('join_date', '').strip(),
                'part': request.form.get('part', '').strip(),
                'role': request.form.get('role', '').strip()
            }
            
            # 필수 필드 확인
            if not all(user_data.values()):
                flash("모든 필드를 입력해주세요.", "error")
                return redirect(url_for('edit_user', user_id=user_id))
            
            result = user_service.update_user(user_id, user_data)
            flash(result['message'], result['type'])
            
            if result['success']:
                return redirect(url_for('admin_dashboard'))
        
        return render_template('edit_user.html', user=user)
        
    except Exception as e:
        flash("사용자 정보 수정 처리 중 오류가 발생했습니다.", "error")
        return redirect(url_for('admin_dashboard'))


@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    try:
        result = user_service.delete_user(user_id)
        flash(result['message'], result['type'])
    except Exception as e:
        flash("사용자 삭제 처리 중 오류가 발생했습니다.", "error")
    
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/reset_password/<int:user_id>', methods=['POST'])
@admin_required
def reset_password(user_id):
    try:
        result = user_service.reset_password(user_id)
        flash(result['message'], result['type'])
    except Exception as e:
        flash("비밀번호 초기화 처리 중 오류가 발생했습니다.", "error")
    
    return redirect(url_for('admin_dashboard'))


# Error Handlers
@app.errorhandler(403)
def forbidden_error(error):
    return render_template('errors/403.html'), 403


@app.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('errors/500.html'), 500


# Security Headers
@app.after_request
def after_request(response):
    """보안 헤더 추가"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
