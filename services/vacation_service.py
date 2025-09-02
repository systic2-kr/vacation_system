# services/vacation_service.py
from models import User, Vacation, db
from services.notification_service import NotificationService
from utils.vacation_calculator import VacationCalculator
from constants import VacationStatus, UserRole
from datetime import date


class VacationService:
    def __init__(self):
        self.notification_service = NotificationService()
        self.calculator = VacationCalculator()
    
    def apply_vacation(self, username, vacation_data):
        try:
            user_info = User.query.filter_by(username=username).first()
            if not user_info:
                return {
                    'success': False,
                    'message': "사용자를 찾을 수 없습니다.",
                    'type': 'error'
                }
            
            # 날짜 변환
            start_date = date.fromisoformat(vacation_data['start_date'])
            end_date = date.fromisoformat(vacation_data['end_date'])
            
            # 과거 날짜 체크
            if start_date < date.today():
                return {
                    'success': False,
                    'message': "과거 날짜로는 휴가를 신청할 수 없습니다.",
                    'type': 'error'
                }
            
            # 3개월 미만 근무자 체크
            if not self.calculator.can_use_annual_leave(user_info.join_date):
                return {
                    'success': False,
                    'message': "입사 후 3개월이 지나야 연차를 사용할 수 있습니다.",
                    'type': 'error'
                }
            
            # 휴가 중복 체크
            overlap_check = self._check_vacation_overlap(username, start_date, end_date)
            if not overlap_check['success']:
                return overlap_check
            
            # 연차 잔여일수 체크
            leave_check = self._check_annual_leave_balance(user_info, vacation_data, start_date, end_date)
            if not leave_check['success']:
                return leave_check
            
            # 결재 상태 결정 - 보안 강화
            status = self._determine_approval_status(user_info.role)
            
            # 휴가 신청 생성
            new_vacation = Vacation(
                applicant=username,
                vacation_type=vacation_data['vacation_type'],
                start_date=vacation_data['start_date'],
                end_date=vacation_data['end_date'],
                reason=vacation_data['reason'],
                backup=vacation_data['backup'],
                status=status
            )
            
            db.session.add(new_vacation)
            db.session.commit()
            
            # 알림 발송
            self._send_application_notification(user_info, status)
            
            return {
                'success': True,
                'message': "휴가 신청이 완료되었습니다. 결재 대기 중입니다.",
                'type': 'success'
            }
            
        except Exception as e:
            db.session.rollback()
            return {
                'success': False,
                'message': "휴가 신청 중 오류가 발생했습니다.",
                'type': 'error'
            }
    
    def cancel_vacation(self, vacation_id, username):
        try:
            vacation = Vacation.query.get_or_404(vacation_id)
            
            if vacation.applicant != username:
                return {
                    'success': False,
                    'message': "자신이 신청한 휴가만 취소할 수 있습니다.",
                    'type': 'error'
                }
            
            if vacation.status in [VacationStatus.PENDING_PART_LEADER, VacationStatus.PENDING_TEAM_LEADER]:
                db.session.delete(vacation)
                db.session.commit()
                return {
                    'success': True,
                    'message': "휴가 신청이 취소되었습니다.",
                    'type': 'success'
                }
            else:
                return {
                    'success': False,
                    'message': "이미 승인/반려된 휴가는 취소할 수 없습니다.",
                    'type': 'error'
                }
                
        except Exception as e:
            db.session.rollback()
            return {
                'success': False,
                'message': "휴가 취소 중 오류가 발생했습니다.",
                'type': 'error'
            }
    
    def approve_vacation(self, vacation_id, approver_username):
        try:
            approver_user = User.query.filter_by(username=approver_username).first()
            if not approver_user:
                return {
                    'success': False,
                    'message': "승인자를 찾을 수 없습니다.",
                    'type': 'error'
                }
                
            vacation = Vacation.query.get_or_404(vacation_id)
            current_status = vacation.status
            
            # 권한 및 상태 검증을 별도 메서드로 분리
            validation_result = self._validate_approval_permission(approver_user, current_status)
            if not validation_result['success']:
                return validation_result
            
            new_status = validation_result['new_status']
            vacation.status = new_status
            db.session.commit()
            
            # 알림 발송
            self._send_approval_notification(vacation, new_status)
            
            return {
                'success': True,
                'message': "결재가 승인되었습니다.",
                'type': 'success'
            }
            
        except Exception as e:
            db.session.rollback()
            return {
                'success': False,
                'message': "결재 승인 중 오류가 발생했습니다.",
                'type': 'error'
            }
    
    def reject_vacation(self, vacation_id, approver_username):
        try:
            approver_user = User.query.filter_by(username=approver_username).first()
            if not approver_user:
                return {
                    'success': False,
                    'message': "승인자를 찾을 수 없습니다.",
                    'type': 'error'
                }
                
            vacation = Vacation.query.get_or_404(vacation_id)
            
            # 권한 검증 강화
            if not self._has_approval_permission(approver_user.role):
                return {
                    'success': False,
                    'message': "결재 권한이 없습니다.",
                    'type': 'error'
                }
            
            if vacation.status not in [VacationStatus.PENDING_PART_LEADER, VacationStatus.PENDING_TEAM_LEADER]:
                return {
                    'success': False,
                    'message': "이미 처리된 결재입니다.",
                    'type': 'error'
                }
            
            vacation.status = VacationStatus.REJECTED
            db.session.commit()
            
            # 신청자에게 알림
            applicant_user = User.query.filter_by(username=vacation.applicant).first()
            if applicant_user:
                message = f"휴가 신청({vacation.start_date})이(가) 반려되었습니다."
                self.notification_service.create_notification(applicant_user.id, message)
            
            return {
                'success': True,
                'message': "결재가 반려되었습니다.",
                'type': 'success'
            }
            
        except Exception as e:
            db.session.rollback()
            return {
                'success': False,
                'message': "결재 반려 중 오류가 발생했습니다.",
                'type': 'error'
            }
    
    def get_user_vacation_history(self, username):
        try:
            return Vacation.query.filter_by(applicant=username).order_by(Vacation.start_date.desc()).all()
        except Exception as e:
            return []
    
    def get_pending_approvals(self, approver_username):
        try:
            approver_user = User.query.filter_by(username=approver_username).first()
            if not approver_user:
                return []
                
            approval_list = []
            
            # 파트장 권한 확인 - 보안 강화
            if self._is_part_leader(approver_user.role):
                pending_vacations = Vacation.query.filter_by(status=VacationStatus.PENDING_PART_LEADER).all()
                for vacation in pending_vacations:
                    applicant_user = User.query.filter_by(username=vacation.applicant).first()
                    # 같은 파트 직원의 신청만 처리 가능
                    if applicant_user and applicant_user.part == approver_user.part:
                        approval_list.append({
                            'id': vacation.id,
                            'applicant': vacation.applicant,
                            'details': vacation
                        })

            # 팀장 권한 확인 - 보안 강화
            if self._is_team_leader(approver_user.role):
                pending_vacations = Vacation.query.filter_by(status=VacationStatus.PENDING_TEAM_LEADER).all()
                for vacation in pending_vacations:
                    approval_list.append({
                        'id': vacation.id,
                        'applicant': vacation.applicant,
                        'details': vacation
                    })

            return approval_list
            
        except Exception as e:
            return []
    
    def _determine_approval_status(self, user_role):
        """사용자 역할에 따른 초기 승인 상태를 결정합니다."""
        if self._is_part_leader(user_role):
            return VacationStatus.PENDING_TEAM_LEADER
        else:
            return VacationStatus.PENDING_PART_LEADER
    
    def _validate_approval_permission(self, approver_user, current_status):
        """승인 권한 및 상태를 검증합니다."""
        user_role = approver_user.role
        
        if self._is_team_leader(user_role) and current_status == VacationStatus.PENDING_TEAM_LEADER:
            return {
                'success': True,
                'new_status': VacationStatus.APPROVED
            }
        elif self._is_part_leader(user_role) and current_status == VacationStatus.PENDING_PART_LEADER:
            return {
                'success': True,
                'new_status': VacationStatus.PENDING_TEAM_LEADER
            }
        else:
            return {
                'success': False,
                'message': "해당 결재를 처리할 권한이 없습니다.",
                'type': 'error'
            }
    
    def _has_approval_permission(self, user_role):
        """결재 권한이 있는지 확인합니다."""
        return self._is_part_leader(user_role) or self._is_team_leader(user_role)
    
    def _is_team_leader(self, user_role):
        """팀장 권한 확인 - 보안 강화"""
        return UserRole.TEAM_LEADER in user_role.split(',')
    
    def _is_part_leader(self, user_role):
        """파트장 권한 확인 - 보안 강화"""
        return UserRole.PART_LEADER in user_role.split(',')
    
    def _check_vacation_overlap(self, username, new_start_date, new_end_date):
        try:
            existing_vacations = Vacation.query.filter_by(applicant=username).filter(
                Vacation.status.in_([
                    VacationStatus.PENDING_PART_LEADER,
                    VacationStatus.PENDING_TEAM_LEADER,
                    VacationStatus.APPROVED
                ])
            ).all()
            
            for vacation in existing_vacations:
                existing_start = date.fromisoformat(vacation.start_date)
                existing_end = date.fromisoformat(vacation.end_date)
                
                if not (new_end_date < existing_start or new_start_date > existing_end):
                    return {
                        'success': False,
                        'message': "해당 기간에 이미 신청된 휴가가 있습니다.",
                        'type': 'error'
                    }
            
            return {'success': True}
            
        except Exception as e:
            return {
                'success': False,
                'message': "휴가 중복 확인 중 오류가 발생했습니다.",
                'type': 'error'
            }
    
    def _check_annual_leave_balance(self, user_info, vacation_data, start_date, end_date):
        try:
            total_annual_leave = self.calculator.calculate_annual_leave(user_info.join_date)
            used_annual_leave = self._calculate_used_annual_leave(user_info.username)
            
            if vacation_data['vacation_type'] == 'annual':
                requested_days = (end_date - start_date).days + 1
            elif vacation_data['vacation_type'] in ['am_half_day', 'pm_half_day']:
                requested_days = 0.5
            else:
                requested_days = 0
            
            if used_annual_leave + requested_days > total_annual_leave:
                remaining = total_annual_leave - used_annual_leave
                return {
                    'success': False,
                    'message': f"연차 신청 가능 일수를 초과했습니다. 현재 신청 가능한 잔여 연차: {remaining}일",
                    'type': 'error'
                }
            
            return {'success': True}
            
        except Exception as e:
            return {
                'success': False,
                'message': "연차 잔여일수 확인 중 오류가 발생했습니다.",
                'type': 'error'
            }
    
    def _calculate_used_annual_leave(self, username):
        try:
            existing_vacations = Vacation.query.filter_by(applicant=username).filter(
                Vacation.status.in_([
                    VacationStatus.APPROVED,
                    VacationStatus.PENDING_PART_LEADER,
                    VacationStatus.PENDING_TEAM_LEADER
                ])
            ).all()
            
            used_days = 0
            
            for vacation in existing_vacations:
                if vacation.vacation_type == 'annual':
                    start = date.fromisoformat(vacation.start_date)
                    end = date.fromisoformat(vacation.end_date)
                    used_days += (end - start).days + 1
                elif vacation.vacation_type in ['am_half_day', 'pm_half_day']:
                    used_days += 0.5
            
            return used_days
            
        except Exception as e:
            return 0  # 오류 시 0으로 반환하여 안전하게 처리
    
    def _send_application_notification(self, user_info, status):
        try:
            if status == VacationStatus.PENDING_TEAM_LEADER:
                # 팀장에게 알림 - 보안 강화된 쿼리
                team_leaders = User.query.filter(
                    User.role.contains(UserRole.TEAM_LEADER)
                ).all()
                
                for team_leader in team_leaders:
                    message = f"{user_info.username}님의 휴가 신청이 도착했습니다."
                    self.notification_service.create_notification(team_leader.id, message)
            else:
                # 파트장에게 알림 - 명시적 조건 사용
                part_leader = User.query.filter(
                    User.part == user_info.part,
                    User.role.contains(UserRole.PART_LEADER)
                ).first()
                
                if part_leader:
                    message = f"{user_info.username}님의 휴가 신청이 도착했습니다."
                    self.notification_service.create_notification(part_leader.id, message)
                    
        except Exception as e:
            # 알림 전송 실패는 전체 프로세스를 중단시키지 않음
            pass
    
    def _send_approval_notification(self, vacation, new_status):
        try:
            if new_status == VacationStatus.PENDING_TEAM_LEADER:
                # 팀장에게 알림 - 보안 강화된 쿼리
                team_leaders = User.query.filter(
                    User.role.contains(UserRole.TEAM_LEADER)
                ).all()
                
                for team_leader in team_leaders:
                    message = f"{vacation.applicant}님의 휴가 신청이 파트장 승인을 완료했습니다."
                    self.notification_service.create_notification(team_leader.id, message)
                    
            elif new_status == VacationStatus.APPROVED:
                # 신청자에게 알림
                applicant_user = User.query.filter_by(username=vacation.applicant).first()
                if applicant_user:
                    message = f"휴가 신청({vacation.start_date})이(가) 최종 승인되었습니다."
                    self.notification_service.create_notification(applicant_user.id, message)
                    
        except Exception as e:
            # 알림 전송 실패는 전체 프로세스를 중단시키지 않음
            pass
