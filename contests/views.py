from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.conf import settings

from .models import UserTeam, UserTeamPlayer, Contest, ContestEntry
from .serializers import (
    CreateTeamSerializer,
    UserTeamSerializer,
    UserTeamListSerializer,
    ContestListSerializer,
    ContestDetailSerializer,
    JoinContestSerializer,
    ContestEntrySerializer,
)
from payments.models import Transaction

from .models import UserTeam, UserTeamPlayer
from .serializers import (
    CreateTeamSerializer,
    UserTeamSerializer,
    UserTeamListSerializer,
)
from matches.models import Match, Squad


class CreateTeamView(APIView):
    """
    Create a fantasy team for a match.
    POST /api/contests/teams/create/
    Requires JWT auth.

    Body:
    {
        "match_id": "uuid",
        "name": "My Team 1",
        "player_ids": ["uuid1", "uuid2", ... 11 total],
        "captain_id": "uuid",
        "vice_captain_id": "uuid"
    }
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        serializer = CreateTeamSerializer(
            data=request.data,
            context={'request': request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        match = data['match']
        squad_entries = data['squad_entries']

        # Build a quick lookup: player_id → squad entry
        squad_map = {str(sq.player_id): sq for sq in squad_entries}

        # Create the UserTeam
        team = UserTeam.objects.create(
            user=request.user,
            match=match,
            name=data['name'],
            captain_id=data['captain_id'],
            vice_captain_id=data['vice_captain_id'],
        )

        # Create 11 UserTeamPlayer rows
        team_players = []
        for player_id in data['player_ids']:
            pid_str = str(player_id)
            multiplier = 1.0
            if pid_str == str(data['captain_id']):
                multiplier = 2.0        # Captain 2x
            elif pid_str == str(data['vice_captain_id']):
                multiplier = 1.5        # VC 1.5x

            team_players.append(UserTeamPlayer(
                team=team,
                player_id=player_id,
                multiplier=multiplier,
            ))

        UserTeamPlayer.objects.bulk_create(team_players)

        # Return the full team
        response_serializer = UserTeamSerializer(team)
        return Response({
            'message': 'Team created successfully!',
            'team': response_serializer.data,
            'credits_used': data['total_credits'],
            'credits_remaining': settings.TOP11_TEAM_BUDGET - data['total_credits'],
        }, status=status.HTTP_201_CREATED)


class MyTeamsView(APIView):
    """
    List all teams created by the logged-in user.
    GET /api/contests/teams/              → all teams
    GET /api/contests/teams/?match_id=uuid → teams for one match
    Requires JWT auth.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        teams = UserTeam.objects.filter(
            user=request.user
        ).select_related('match__team_a', 'match__team_b', 'captain', 'vice_captain')

        match_id = request.query_params.get('match_id')
        if match_id:
            teams = teams.filter(match_id=match_id)

        teams = teams.order_by('-created_at')
        serializer = UserTeamListSerializer(teams, many=True)
        return Response({
            'count': teams.count(),
            'teams': serializer.data,
        })


class TeamDetailView(APIView):
    """
    Full detail of one team including all 11 players.
    GET /api/contests/teams/<team_id>/
    Requires JWT auth. User can only see their own teams.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, team_id):
        team = get_object_or_404(
            UserTeam.objects.select_related(
                'match__team_a', 'match__team_b',
                'captain', 'vice_captain'
            ).prefetch_related('team_players__player'),
            id=team_id,
            user=request.user     # User can only see their own team
        )
        serializer = UserTeamSerializer(team)
        return Response(serializer.data)


class EditTeamView(APIView):
    """
    Edit a team (only allowed if match hasn't started).
    PUT /api/contests/teams/<team_id>/edit/
    Requires JWT auth.
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def put(self, request, team_id):
        team = get_object_or_404(
            UserTeam,
            id=team_id,
            user=request.user
        )

        # Cannot edit if team is locked
        if team.is_locked:
            return Response(
                {'error': 'Team is locked. Match has already started.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check match hasn't started
        from django.utils import timezone
        if team.match.squads_locked_at and timezone.now() > team.match.squads_locked_at:
            return Response(
                {'error': 'Cannot edit team after squad lock time.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate new team data
        data = request.data.copy()
        data['match_id'] = str(team.match_id)

        serializer = CreateTeamSerializer(
            data=data,
            context={'request': request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated = serializer.validated_data

        # Delete old players and replace
        team.team_players.all().delete()

        team.captain_id = validated['captain_id']
        team.vice_captain_id = validated['vice_captain_id']
        team.name = validated.get('name', team.name)
        team.save()

        # Recreate 11 player rows
        team_players = []
        for player_id in validated['player_ids']:
            pid_str = str(player_id)
            multiplier = 1.0
            if pid_str == str(validated['captain_id']):
                multiplier = 2.0
            elif pid_str == str(validated['vice_captain_id']):
                multiplier = 1.5

            team_players.append(UserTeamPlayer(
                team=team,
                player_id=player_id,
                multiplier=multiplier,
            ))

        UserTeamPlayer.objects.bulk_create(team_players)

        response_serializer = UserTeamSerializer(team)
        return Response({
            'message': 'Team updated successfully!',
            'team': response_serializer.data,
        })


class DeleteTeamView(APIView):
    """
    Delete a team (only if not entered in any contest and match not started).
    DELETE /api/contests/teams/<team_id>/delete/
    Requires JWT auth.
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request, team_id):
        team = get_object_or_404(
            UserTeam,
            id=team_id,
            user=request.user
        )

        if team.is_locked:
            return Response(
                {'error': 'Cannot delete a locked team.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if entered in any contest
        if team.contest_entries.exists():
            return Response(
                {'error': 'Cannot delete a team that is entered in a contest.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        team.delete()
        return Response({'message': 'Team deleted.'}, status=status.HTTP_200_OK)


class ValidateTeamView(APIView):
    """
    Dry-run validation — check if a team is valid WITHOUT saving it.
    Useful for frontend to show errors before submission.
    POST /api/contests/teams/validate/
    Requires JWT auth.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CreateTeamSerializer(
            data=request.data,
            context={'request': request}
        )
        if not serializer.is_valid():
            return Response({
                'valid': False,
                'errors': serializer.errors,
            }, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        return Response({
            'valid': True,
            'credits_used': data['total_credits'],
            'credits_remaining': settings.TOP11_TEAM_BUDGET - data['total_credits'],
            'message': 'Team is valid and ready to submit.',
        })



# Add these imports at the top of contests/views.py
from django.db import transaction
from .models import Contest, ContestEntry
from .serializers import (
    ContestListSerializer,
    ContestDetailSerializer,
    JoinContestSerializer,
    ContestEntrySerializer,
)
from payments.models import Transaction
from accounts.models import Wallet


class ContestListView(APIView):
    """
    List all contests for a match.
    GET /api/contests/?match_id=<uuid>
    Public — no auth needed.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        match_id = request.query_params.get('match_id')
        if not match_id:
            return Response(
                {'error': 'match_id query parameter is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        contests = Contest.objects.filter(
            match_id=match_id
        ).select_related('match__team_a', 'match__team_b').order_by('entry_fee')

        serializer = ContestListSerializer(contests, many=True)
        return Response({
            'count': contests.count(),
            'contests': serializer.data,
        })


class ContestDetailView(APIView):
    """
    Full contest detail with prize breakdown.
    GET /api/contests/<contest_id>/
    Public — no auth needed.
    """
    permission_classes = [AllowAny]

    def get(self, request, contest_id):
        contest = get_object_or_404(
            Contest.objects.select_related('match__team_a', 'match__team_b'),
            id=contest_id
        )
        serializer = ContestDetailSerializer(
            contest, context={'request': request}
        )
        return Response(serializer.data)


class JoinContestView(APIView):
    """
    Join a contest with a team. Deducts entry fee from wallet.
    POST /api/contests/<contest_id>/join/
    Requires JWT auth.

    Body: { "team_id": "uuid" }
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, contest_id):
        contest = get_object_or_404(Contest, id=contest_id)

        serializer = JoinContestSerializer(
            data=request.data,
            context={'request': request, 'contest': contest}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        team = data['team']
        user = request.user

        # --- Deduct entry fee from wallet ---
        if contest.entry_fee > 0:
            wallet = user.wallet

            # Deduct from deposit first, then winnings, then bonus
            remaining_fee = contest.entry_fee
            deposit_deducted = 0
            winnings_deducted = 0
            bonus_deducted = 0

            if wallet.deposit_balance >= remaining_fee:
                deposit_deducted = remaining_fee
                remaining_fee = 0
            else:
                deposit_deducted = wallet.deposit_balance
                remaining_fee -= wallet.deposit_balance

            if remaining_fee > 0:
                if wallet.winnings_balance >= remaining_fee:
                    winnings_deducted = remaining_fee
                    remaining_fee = 0
                else:
                    winnings_deducted = wallet.winnings_balance
                    remaining_fee -= wallet.winnings_balance

            if remaining_fee > 0:
                bonus_deducted = min(wallet.bonus_balance, remaining_fee)
                remaining_fee -= bonus_deducted

            if remaining_fee > 0:
                return Response(
                    {'error': 'Insufficient wallet balance.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Update wallet balances atomically
            wallet.deposit_balance -= deposit_deducted
            wallet.winnings_balance -= winnings_deducted
            wallet.bonus_balance -= bonus_deducted
            wallet.save()

            # Record the transaction
            Transaction.objects.create(
                user=user,
                transaction_type='contest_entry',
                status='success',
                amount=contest.entry_fee,
                wallet_bucket='deposit',
                description=f'Entry fee for {contest.name}',
                idempotency_key=f'entry_{contest.id}_{team.id}',
            )

        # --- Create ContestEntry ---
        entry = ContestEntry.objects.create(
            contest=contest,
            user=user,
            team=team,
            entry_fee_paid=contest.entry_fee,
        )

        # --- Update contest entry count ---
        Contest.objects.filter(id=contest.id).update(
            current_entries=contest.current_entries + 1
        )

        return Response({
            'message': f'Successfully joined {contest.name}!',
            'entry_id': str(entry.id),
            'team': team.name,
            'entry_fee_paid': round(contest.entry_fee / 100, 2),
        }, status=status.HTTP_201_CREATED)


class LeaveContestView(APIView):
    """
    Leave a contest and get refund (only if match hasn't started).
    DELETE /api/contests/<contest_id>/leave/
    Requires JWT auth.
    Body: { "team_id": "uuid" }
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def delete(self, request, contest_id):
        contest = get_object_or_404(Contest, id=contest_id)

        # Can only leave upcoming contests
        if contest.status != 'upcoming':
            return Response(
                {'error': 'Can only leave upcoming contests.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        team_id = request.data.get('team_id')
        entry = get_object_or_404(
            ContestEntry,
            contest=contest,
            user=request.user,
            team_id=team_id,
        )

        # Refund entry fee to deposit balance
        if entry.entry_fee_paid > 0:
            wallet = request.user.wallet
            wallet.deposit_balance += entry.entry_fee_paid
            wallet.save()

            Transaction.objects.create(
                user=request.user,
                transaction_type='refund',
                status='success',
                amount=entry.entry_fee_paid,
                wallet_bucket='deposit',
                description=f'Refund for leaving {contest.name}',
                idempotency_key=f'leave_refund_{entry.id}',
            )

        entry.delete()

        # Decrement contest entry count
        Contest.objects.filter(id=contest.id).update(
            current_entries=max(0, contest.current_entries - 1)
        )

        return Response({'message': 'Left contest. Entry fee refunded to your wallet.'})


class MyContestsView(APIView):
    """
    List all contests the logged-in user has joined.
    GET /api/contests/my-contests/
    GET /api/contests/my-contests/?status=upcoming
    Requires JWT auth.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        entries = ContestEntry.objects.filter(
            user=request.user
        ).select_related(
            'contest__match__team_a',
            'contest__match__team_b',
            'team'
        ).order_by('-joined_at')

        filter_status = request.query_params.get('status')
        if filter_status:
            entries = entries.filter(contest__status=filter_status)

        serializer = ContestEntrySerializer(entries, many=True)
        return Response({
            'count': entries.count(),
            'entries': serializer.data,
        })


class ContestLeaderboardView(APIView):
    """
    Live leaderboard for a contest.
    GET /api/contests/<contest_id>/leaderboard/
    Public — no auth needed.
    """
    permission_classes = [AllowAny]

    def get(self, request, contest_id):
        contest = get_object_or_404(Contest, id=contest_id)

        from scoring.models import Leaderboard
        rankings = Leaderboard.objects.filter(
            contest=contest
        ).select_related(
            'user', 'team'
        ).order_by('rank')[:100]   # Top 100 only

        if not rankings.exists():
            # Match not started yet — show entries in join order
            entries = ContestEntry.objects.filter(
                contest=contest
            ).select_related('user', 'team').order_by('joined_at')[:100]

            data = [{
                'rank': i + 1,
                'user': entry.user.full_name or entry.user.email.split('@')[0],
                'team_name': entry.team.name,
                'points': 0,
                'prize_inr': 0,
            } for i, entry in enumerate(entries)]

            return Response({
                'contest': contest.name,
                'status': contest.status,
                'total_entries': contest.current_entries,
                'rankings': data,
            })

        data = [{
            'rank': r.rank,
            'user': r.user.full_name or r.user.email.split('@')[0],
            'team_name': r.team.name,
            'points': float(r.total_points),
            'prize_inr': round(r.prize_amount / 100, 2),
        } for r in rankings]

        return Response({
            'contest': contest.name,
            'status': contest.status,
            'total_entries': contest.current_entries,
            'rankings': data,
        })


class AdminCreateContestView(APIView):
    """
    Admin creates a contest for a match.
    POST /api/contests/admin/create/
    Admin only.
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        from matches.models import Match
        required = ['match_id', 'name', 'contest_type', 'entry_fee',
                    'total_prize_pool', 'max_entries', 'prize_distribution']

        for field in required:
            if field not in request.data:
                return Response(
                    {'error': f'{field} is required.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        match = get_object_or_404(Match, id=request.data['match_id'])

        contest = Contest.objects.create(
            match=match,
            name=request.data['name'],
            contest_type=request.data['contest_type'],
            entry_fee=int(float(request.data['entry_fee']) * 100),     # Convert ₹ to paise
            total_prize_pool=int(float(request.data['total_prize_pool']) * 100),
            max_entries=request.data['max_entries'],
            min_entries=request.data.get('min_entries', 2),
            max_teams_per_user=request.data.get('max_teams_per_user', 6),
            prize_distribution=request.data['prize_distribution'],
            created_by=request.user,
        )

        serializer = ContestDetailSerializer(contest, context={'request': request})
        return Response({
            'message': 'Contest created successfully!',
            'contest': serializer.data,
        }, status=status.HTTP_201_CREATED)