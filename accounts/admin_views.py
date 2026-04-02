from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from django.db.models import Sum, Count
from django.utils import timezone
from datetime import timedelta

from accounts.models import User, Wallet
from payments.models import Transaction, Withdrawal
from contests.models import Contest, ContestEntry
from matches.models import Match
from top11_project.admin_helpers import log_admin_action, get_client_ip


class DashboardStatsView(APIView):
    """
    Platform-wide stats for admin dashboard.
    GET /api/admin/dashboard/
    Admin only.
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        now = timezone.now()
        today = now.date()
        week_ago = now - timedelta(days=7)

        # User stats
        total_users = User.objects.filter(is_staff=False).count()
        new_users_today = User.objects.filter(
            created_at__date=today, is_staff=False
        ).count()
        kyc_pending = User.objects.filter(is_kyc_done=False, is_staff=False).count()

        # Financial stats
        total_deposits = Transaction.objects.filter(
            transaction_type='deposit', status='success'
        ).aggregate(total=Sum('amount'))['total'] or 0

        total_withdrawals = Transaction.objects.filter(
            transaction_type='withdrawal', status='success'
        ).aggregate(total=Sum('amount'))['total'] or 0

        total_prize_distributed = Transaction.objects.filter(
            transaction_type='prize_credit', status='success'
        ).aggregate(total=Sum('amount'))['total'] or 0

        pending_withdrawals = Withdrawal.objects.filter(
            status='pending'
        ).count()

        pending_withdrawals_amount = Withdrawal.objects.filter(
            status='pending'
        ).aggregate(total=Sum('amount'))['total'] or 0

        # Match stats
        upcoming_matches = Match.objects.filter(status='upcoming').count()
        live_matches = Match.objects.filter(status='live').count()

        # Contest stats
        active_contests = Contest.objects.filter(status='upcoming').count()
        total_entries_week = ContestEntry.objects.filter(
            joined_at__gte=week_ago
        ).count()

        return Response({
            'users': {
                'total': total_users,
                'new_today': new_users_today,
                'kyc_pending': kyc_pending,
            },
            'financials': {
                'total_deposits_inr': round(total_deposits / 100, 2),
                'total_withdrawals_inr': round(total_withdrawals / 100, 2),
                'total_prizes_inr': round(total_prize_distributed / 100, 2),
                'pending_withdrawals_count': pending_withdrawals,
                'pending_withdrawals_inr': round(pending_withdrawals_amount / 100, 2),
            },
            'matches': {
                'upcoming': upcoming_matches,
                'live': live_matches,
            },
            'contests': {
                'active': active_contests,
                'entries_this_week': total_entries_week,
            },
        })


class KYCApproveView(APIView):
    """
    Approve or reject a user's KYC.
    POST /api/admin/kyc/
    Admin only.
    Body: { "user_id": "uuid", "action": "approve" or "reject", "reason": "optional" }
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        user_id = request.data.get('user_id')
        action = request.data.get('action')

        if not user_id or action not in ['approve', 'reject']:
            return Response(
                {'error': 'user_id and action (approve/reject) are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = User.objects.get(id=user_id, is_staff=False)
        except User.DoesNotExist:
            return Response({'error': 'User not found.'}, status=404)

        if action == 'approve':
            user.is_kyc_done = True
            user.pan_verified = True
            user.save()
            log_admin_action(
                request.user, f'KYC approved for {user.email}',
                'User', user.id, ip_address=get_client_ip(request)
            )
            return Response({'message': f'KYC approved for {user.email}.'})

        else:
            user.is_kyc_done = False
            user.pan_verified = False
            user.save()
            log_admin_action(
                request.user, f'KYC rejected for {user.email}: {request.data.get("reason", "")}',
                'User', user.id, ip_address=get_client_ip(request)
            )
            return Response({'message': f'KYC rejected for {user.email}.'})


class BanUserView(APIView):
    """
    Ban or unban a user.
    POST /api/admin/ban-user/
    Admin only.
    Body: { "user_id": "uuid", "action": "ban" or "unban" }
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        user_id = request.data.get('user_id')
        action = request.data.get('action')

        if not user_id or action not in ['ban', 'unban']:
            return Response(
                {'error': 'user_id and action (ban/unban) are required.'},
                status=400
            )

        try:
            user = User.objects.get(id=user_id, is_staff=False)
        except User.DoesNotExist:
            return Response({'error': 'User not found.'}, status=404)

        if action == 'ban':
            user.is_active = False
            user.save()
            log_admin_action(
                request.user, f'User banned: {user.email}',
                'User', user.id, ip_address=get_client_ip(request)
            )
            return Response({'message': f'{user.email} has been banned.'})
        else:
            user.is_active = True
            user.save()
            log_admin_action(
                request.user, f'User unbanned: {user.email}',
                'User', user.id, ip_address=get_client_ip(request)
            )
            return Response({'message': f'{user.email} has been unbanned.'})


class UserDetailAdminView(APIView):
    """
    Full user detail for admin — wallet, transactions, teams.
    GET /api/admin/users/<user_id>/
    Admin only.
    """
    permission_classes = [IsAdminUser]

    def get(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found.'}, status=404)

        try:
            wallet = user.wallet
            wallet_data = {
                'deposit': round(wallet.deposit_balance / 100, 2),
                'winnings': round(wallet.winnings_balance / 100, 2),
                'bonus': round(wallet.bonus_balance / 100, 2),
                'total': round(wallet.total_balance / 100, 2),
            }
        except Exception:
            wallet_data = None

        recent_transactions = Transaction.objects.filter(
            user=user
        ).order_by('-created_at')[:10]

        txn_data = [{
            'type': t.transaction_type,
            'amount': round(t.amount / 100, 2),
            'status': t.status,
            'date': t.created_at.strftime('%Y-%m-%d %H:%M'),
        } for t in recent_transactions]

        return Response({
            'id': str(user.id),
            'email': user.email,
            'full_name': user.full_name,
            'mobile': user.mobile,
            'is_active': user.is_active,
            'is_verified': user.is_verified,
            'is_kyc_done': user.is_kyc_done,
            'pan_number': user.pan_number,
            'created_at': user.created_at.strftime('%Y-%m-%d'),
            'wallet': wallet_data,
            'recent_transactions': txn_data,
        })


class PlatformUsersListView(APIView):
    """
    List all users with search and filter.
    GET /api/admin/users/?search=yuvraj&kyc=pending
    Admin only.
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        users = User.objects.filter(is_staff=False).order_by('-created_at')

        search = request.query_params.get('search', '')
        kyc = request.query_params.get('kyc', '')
        active = request.query_params.get('active', '')

        if search:
            users = users.filter(email__icontains=search) | \
                    users.filter(full_name__icontains=search)
        if kyc == 'pending':
            users = users.filter(is_kyc_done=False)
        elif kyc == 'verified':
            users = users.filter(is_kyc_done=True)
        if active == 'false':
            users = users.filter(is_active=False)

        users = users[:50]
        data = [{
            'id': str(u.id),
            'email': u.email,
            'full_name': u.full_name,
            'is_active': u.is_active,
            'is_kyc_done': u.is_kyc_done,
            'created_at': u.created_at.strftime('%Y-%m-%d'),
        } for u in users]

        return Response({'count': len(data), 'users': data})