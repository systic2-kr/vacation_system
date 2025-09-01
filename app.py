# app.py
from flask import Flask, render_template, request, redirect, url_for, session, flash
from config import Config
from models import db, User, Vacation, Notification
from services.vacation_service import VacationService
from services.user_service import UserService
from services.notification_service import NotificationService
from services.auth_service import AuthService
from utils.decorators import login_required, admin_required
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
        username = request.form['username']
        password = request.form['password']
        
        result = auth_service.authenticate_user(username, password)
        
        if result['success']:
            session['username'] = username
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
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        result = auth_service.change_password(username, new_password, confirm_password)
        flash(result['message'], result['type'])
        
        if result['success']:
            return redirect(url_for('dashboard'))
        
        return redirect(url_for('change_password'))

    return render_template('change_password.html')


@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))


# Dashboard
@app.route('/dashboard')
@login_required
def dashboard():
    username = session['username']
    user_info = user_service.get_user_by_username(username)
    unread_count = notification_service.get_unread_count(user_info.id)
    user_roles = user_info.role.split(',')
    
    return render_template('dashboard.html', 
                           username=username, 
                           user_roles=user_roles, 
                           unread_notifications_count=unread_count)


# Vacation Routes
@app.route('/apply', methods=['GET', 'POST'])
@login_required
def apply_vacation():  # 함수명 수정
    username = session['username']
    
    if request.method == 'POST':
        vacation_data = {
            'vacation_type': request.form['vacation_type'],
            'start_date': request.form['start_date'],
            'end_date': request.form['end_date'],
            'reason': request.form['reason'],
            'backup': request.form['backup']
        }
        
        result = vacation_service.apply_vacation(username, vacation_data)
        flash(result['message'], result['type'])
        
        if result['success']:
            return redirect(url_for('dashboard'))
        
        return redirect(url_for('apply_vacation'))
    
    return render_template('apply.html')


@app.route('/history')
@login_required
def history():
    username = session['username']
    vacation_history = vacation_service.get_user_vacation_history(username)
    return render_template('history.html', history=vacation_history)


@app.route('/history/cancel/<int:vacation_id>', methods=['POST'])
@login_required
def cancel_vacation(vacation_id):
    username = session['username']
    result = vacation_service.cancel_vacation(vacation_id, username)
    flash(result['message'], result['type'])
    return redirect(url_for('history'))


# Approval Routes
@app.route('/approvals')
@login_required
def approvals():
    username = session['username']
    approval_list = vacation_service.get_pending_approvals(username)
    return render_template('approvals.html', approval_list=approval_list)


@app.route('/approvals/approve/<int:vacation_id>', methods=['POST'])
@login_required
def approve_vacation(vacation_id):
    username = session['username']
    result = vacation_service.approve_vacation(vacation_id, username)
    flash(result['message'], result['type'])
    return redirect(url_for('approvals'))


@app.route('/approvals/reject/<int:vacation_id>', methods=['POST'])
@login_required
def reject_vacation(vacation_id):
    username = session['username']
    result = vacation_service.reject_vacation(vacation_id, username)
    flash(result['message'], result['type'])
    return redirect(url_for('approvals'))


# Notification Routes
@app.route('/notifications')
@login_required
def notifications():
    username = session['username']
    user = user_service.get_user_by_username(username)
    user_notifications = notification_service.get_user_notifications(user.id)
    notification_service.mark_all_as_read(user.id)
    
    return render_template('notifications.html', notifications=user_notifications)


# Admin Routes
@app.route('/admin')
@admin_required
def admin_dashboard():  # 함수명 수정
    users = user_service.get_all_users()
    return render_template('admin_dashboard.html', users=users)


@app.route('/admin/add_user', methods=['GET', 'POST'])
@admin_required
def add_user():
    if request.method == 'POST':
        user_data = {
            'username': request.form['username'],
            'join_date': request.form['join_date'],
            'part': request.form['part'],
            'role': request.form['role']
        }
        
        result = user_service.create_user(user_data)
        flash(result['message'], result['type'])
        
        if result['success']:
            return redirect(url_for('admin_dashboard'))

    return render_template('add_user.html')


@app.route('/admin/edit_user/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def edit_user(user_id):
    user = user_service.get_user_by_id(user_id)
    
    if request.method == 'POST':
        user_data = {
            'username': request.form['username'],
            'join_date': request.form['join_date'],
            'part': request.form['part'],
            'role': request.form['role']
        }
        
        result = user_service.update_user(user_id, user_data)
        flash(result['message'], result['type'])
        
        if result['success']:
            return redirect(url_for('admin_dashboard'))
    
    return render_template('edit_user.html', user=user)


@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    result = user_service.delete_user(user_id)
    flash(result['message'], result['type'])
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/reset_password/<int:user_id>', methods=['POST'])
@admin_required
def reset_password(user_id):
    result = user_service.reset_password(user_id)
    flash(result['message'], result['type'])
    return redirect(url_for('admin_dashboard'))


# Error Handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('errors/500.html'), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
