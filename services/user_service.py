# services/user_service.py
from werkzeug.security import generate_password_hash
from models import User, db
from constants import AppConfig, UserRole
import re
from datetime import date


class UserService:
    def get_user_by_username(self, username):
        """사용자명으로 사용자 조회"""
        try:
            # 입력값 검증
            if not username or not isinstance(username, str):
                return None
            
            # SQL 인젝션 방지를 위한 안전한 쿼리
            return User.query.filter_by(username=username.strip()).first()
        except Exception as e:
            return None
    
    def get_user_by_id(self, user_id):
        """사용자 ID로 사용자 조회"""
        try:
            # 입력값 검증
            if not isinstance(user_id, int) or user_id <= 0:
                return None
            
            return User.query.get_or_404(user_id)
        except Exception as e:
            return None
    
    def get_all_users(self):
        """모든 사용자 조회"""
        try:
            return User.query.all()
        except Exception as e:
            return []
    
    def create_user(self, user_data):
        """새 사용자 생성"""
        try:
            # 입력 데이터 검증
            validation_result = self._validate_user_data(user_data)
            if not validation_result['valid']:
                return {
                    'success': False,
                    'message': validation_result['message'],
                    'type': 'error'
                }
            
            # 중복 사용자명 확인
            if User.query.filter_by(username=user_data['username'].strip()).first():
                return {
                    'success': False,
                    'message': "이미 존재하는 사용자 아이디입니다.",
                    'type': 'error'
                }
            
            # 임시 비밀번호 생성
            temp_password = AppConfig.TEMP_PASSWORD
            hashed_password = generate_password_hash(temp_password)
            
            new_user = User(
                username=user_data['username'].strip(),
                password=hashed_password,
                join_date=user_data['join_date'],
                part=user_data['part'].strip(),
                role=user_data['role'].strip(),
                is_temp_password=True
            )
            
            db.session.add(new_user)
            db.session.commit()
            
            return {
                'success': True,
                'message': f"{user_data['username']} 사용자가 성공적으로 추가되었습니다. 임시 비밀번호는 '{temp_password}'입니다.",
                'type': 'success'
            }
            
        except Exception as e:
            db.session.rollback()
            return {
                'success': False,
                'message': "사용자 생성 중 오류가 발생했습니다.",
                'type': 'error'
            }
    
    def update_user(self, user_id, user_data):
        """사용자 정보 수정"""
        try:
            # 입력 데이터 검증
            validation_result = self._validate_user_data(user_data, is_update=True)
            if not validation_result['valid']:
                return {
                    'success': False,
                    'message': validation_result['message'],
                    'type': 'error'
                }
            
            user = self.get_user_by_id(user_id)
            if not user:
                return {
                    'success': False,
                    'message': "사용자를 찾을 수 없습니다.",
                    'type': 'error'
                }
            
            # 사용자명 중복 확인 (자신 제외)
            existing_user = User.query.filter_by(username=user_data['username'].strip()).first()
            if existing_user and existing_user.id != user_id:
                return {
                    'success': False,
                    'message': "이미 존재하는 사용자 아이디입니다.",
                    'type': 'error'
                }
            
            # 사용자 정보 업데이트
            user.username = user_data['username'].strip()
            user.join_date = user_data['join_date']
            user.part = user_data['part'].strip()
            user.role = user_data['role'].strip()
            
            db.session.commit()
            
            return {
                'success': True,
                'message': "사용자 정보가 성공적으로 수정되었습니다.",
                'type': 'success'
            }
            
        except Exception as e:
            db.session.rollback()
            return {
                'success': False,
                'message': "사용자 정보 수정 중 오류가 발생했습니다.",
                'type': 'error'
            }
    
    def delete_user(self, user_id):
        """사용자 삭제"""
        try:
            user = self.get_user_by_id(user_id)
            if not user:
                return {
                    'success': False,
                    'message': "사용자를 찾을 수 없습니다.",
                    'type': 'error'
                }
            
            # 관리자 계정 삭제 방지
            if 'admin' in user.username.lower():
                return {
                    'success': False,
                    'message': "관리자 계정은 삭제할 수 없습니다.",
                    'type': 'error'
                }
            
            username = user.username  # 삭제 전에 이름 저장
            db.session.delete(user)
            db.session.commit()
            
            return {
                'success': True,
                'message': f"{username} 사용자가 성공적으로 삭제(퇴사)되었습니다.",
                'type': 'success'
            }
            
        except Exception as e:
            db.session.rollback()
            return {
                'success': False,
                'message': "사용자 삭제 중 오류가 발생했습니다.",
                'type': 'error'
            }
    
    def reset_password(self, user_id):
        """사용자 비밀번호 초기화"""
        try:
            user = self.get_user_by_id(user_id)
            if not user:
                return {
                    'success': False,
                    'message': "사용자를 찾을 수 없습니다.",
                    'type': 'error'
                }
            
            # 관리자 계정 비밀번호 초기화 방지
            if 'admin' in user.username.lower():
                return {
                    'success': False,
                    'message': "관리자 계정의 비밀번호는 초기화할 수 없습니다.",
                    'type': 'error'
                }
            
            temp_password = AppConfig.TEMP_PASSWORD
            
            user.password = generate_password_hash(temp_password)
            user.is_temp_password = True
            db.session.commit()
            
            return {
                'success': True,
                'message': f"{user.username}의 비밀번호가 '{temp_password}'로 초기화되었습니다. 사용자는 로그인 후 즉시 비밀번호를 변경해야 합니다.",
                'type': 'success'
            }
            
        except Exception as e:
            db.session.rollback()
            return {
                'success': False,
                'message': "비밀번호 초기화 중 오류가 발생했습니다.",
                'type': 'error'
            }
    
    def _validate_user_data(self, user_data, is_update=False):
        """사용자 데이터 유효성 검증"""
        try:
            # 필수 필드 확인
            required_fields = ['username', 'join_date', 'part', 'role']
            for field in required_fields:
                if field not in user_data or not user_data[field]:
                    return {
                        'valid': False,
                        'message': f"{field} 필드는 필수입니다."
                    }
            
            # 사용자명 검증
            username = user_data['username'].strip()
            if not self._validate_username(username):
                return {
                    'valid': False,
                    'message': "사용자명은 3-20자의 영문, 숫자, 언더스코어만 사용 가능합니다."
                }
            
            # 날짜 형식 검증
            try:
                date.fromisoformat(user_data['join_date'])
            except ValueError:
                return {
                    'valid': False,
                    'message': "올바른 날짜 형식이 아닙니다. (YYYY-MM-DD)"
                }
            
            # 부서명 검증
            part = user_data['part'].strip()
            if not self._validate_part_name(part):
                return {
                    'valid': False,
                    'message': "부서명은 1-50자의 한글, 영문만 사용 가능합니다."
                }
            
            # 역할 검증
            role = user_data['role'].strip()
            if not self._validate_role(role):
                return {
                    'valid': False,
                    'message': "유효하지 않은 역할입니다. (팀장, 파트장, 팀원 중 선택)"
                }
            
            return {'valid': True}
            
        except Exception as e:
            return {
                'valid': False,
                'message': "데이터 검증 중 오류가 발생했습니다."
            }
    
    def _validate_username(self, username):
        """사용자명 형식 검증"""
        # 3-20자의 영문, 숫자, 언더스코어만 허용
        pattern = r'^[a-zA-Z0-9_]{3,20}$'
        return bool(re.match(pattern, username))
    
    def _validate_part_name(self, part):
        """부서명 형식 검증"""
        # 1-50자의 한글, 영문, 공백 허용
        pattern = r'^[가-힣a-zA-Z\s]{1,50}$'
        return bool(re.match(pattern, part))
    
    def _validate_role(self, role):
        """역할 유효성 검증"""
        valid_roles = [UserRole.TEAM_LEADER, UserRole.PART_LEADER, UserRole.MEMBER]
        
        # 쉼표로 구분된 역할들 검증
        roles = [r.strip() for r in role.split(',')]
        
        # 모든 역할이 유효한지 확인
        for r in roles:
            if r not in valid_roles:
                return False
        
        return len(roles) > 0  # 최소 하나의 역할은 있어야 함
    
    def get_users_by_role(self, role):
        """특정 역할을 가진 사용자들 조회"""
        try:
            return User.query.filter(User.role.contains(role)).all()
        except Exception as e:
            return []
    
    def get_users_by_part(self, part):
        """특정 부서의 사용자들 조회"""
        try:
            return User.query.filter_by(part=part).all()
        except Exception as e:
            return []
    
    def is_user_exists(self, username):
        """사용자 존재 여부 확인"""
        try:
            return User.query.filter_by(username=username.strip()).first() is not None
        except Exception as e:
            return False
    
    def get_user_stats(self):
        """사용자 통계 정보 반환"""
        try:
            total_users = User.query.count()
            temp_password_users = User.query.filter_by(is_temp_password=True).count()
            
            return {
                'total_users': total_users,
                'temp_password_users': temp_password_users,
                'active_users': total_users - temp_password_users
            }
        except Exception as e:
            return {
                'total_users': 0,
                'temp_password_users': 0,
                'active_users': 0
            }
