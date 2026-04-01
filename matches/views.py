from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import Match, Player, CricketTeam, Squad
from .serializers import (
    MatchListSerializer,
    MatchDetailSerializer,
    PlayerSerializer,
    SquadPlayerSerializer,
    CricketTeamSerializer,
)


class UpcomingMatchListView(APIView):
    """
    List all upcoming matches.
    GET /api/matches/upcoming/
    Public — no auth needed.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        matches = Match.objects.filter(
            status='upcoming',
            scheduled_at__gt=timezone.now()
        ).select_related('team_a', 'team_b').order_by('scheduled_at')

        serializer = MatchListSerializer(matches, many=True)
        return Response({
            'count': matches.count(),
            'matches': serializer.data
        })


class LiveMatchListView(APIView):
    """
    List all live matches.
    GET /api/matches/live/
    Public — no auth needed.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        matches = Match.objects.filter(
            status='live'
        ).select_related('team_a', 'team_b').order_by('scheduled_at')

        serializer = MatchListSerializer(matches, many=True)
        return Response({
            'count': matches.count(),
            'matches': serializer.data
        })


class CompletedMatchListView(APIView):
    """
    List recently completed matches.
    GET /api/matches/completed/
    Public — no auth needed.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        matches = Match.objects.filter(
            status='completed'
        ).select_related('team_a', 'team_b').order_by('-scheduled_at')[:20]

        serializer = MatchListSerializer(matches, many=True)
        return Response({
            'count': len(matches),
            'matches': serializer.data
        })


class MatchDetailView(APIView):
    """
    Full match detail including squad players with credits.
    GET /api/matches/<match_id>/
    Public — no auth needed.
    """
    permission_classes = [AllowAny]

    def get(self, request, match_id):
        match = get_object_or_404(
            Match.objects.select_related('team_a', 'team_b', 'winner'),
            id=match_id
        )
        serializer = MatchDetailSerializer(match)
        return Response(serializer.data)


class MatchPlayersView(APIView):
    """
    List all players in a match squad with their fantasy credits,
    grouped by team and role — used for the team selection screen.
    GET /api/matches/<match_id>/players/
    Public — no auth needed.
    """
    permission_classes = [AllowAny]

    def get(self, request, match_id):
        match = get_object_or_404(Match, id=match_id)
        squads = Squad.objects.filter(
            match=match
        ).select_related('player', 'team').order_by('team__name', 'player__role')

        # Group by team
        team_a_players = []
        team_b_players = []

        for squad in squads:
            player_data = {
                'squad_id': str(squad.id),
                'player_id': str(squad.player.id),
                'name': squad.player.name,
                'role': squad.player.role,
                'country': squad.player.country,
                'fantasy_credit': float(squad.fantasy_credit),
                'is_playing_xi': squad.is_playing_xi,
                'is_announced': squad.is_announced,
                'photo': request.build_absolute_uri(squad.player.photo.url) if squad.player.photo else None,
                'team_short': squad.team.short_name,
            }
            if squad.team == match.team_a:
                team_a_players.append(player_data)
            else:
                team_b_players.append(player_data)

        return Response({
            'match_id': str(match.id),
            'match_status': match.status,
            'squads_locked': match.squads_locked_at is not None and timezone.now() > match.squads_locked_at,
            'team_a': {
                'id': str(match.team_a.id),
                'name': match.team_a.name,
                'short_name': match.team_a.short_name,
                'players': team_a_players,
            },
            'team_b': {
                'id': str(match.team_b.id),
                'name': match.team_b.name,
                'short_name': match.team_b.short_name,
                'players': team_b_players,
            },
            'total_players': len(team_a_players) + len(team_b_players),
        })


class PlayerDetailView(APIView):
    """
    Individual player info.
    GET /api/matches/players/<player_id>/
    Public — no auth needed.
    """
    permission_classes = [AllowAny]

    def get(self, request, player_id):
        player = get_object_or_404(Player, id=player_id)
        serializer = PlayerSerializer(player)
        return Response(serializer.data)


class PlayerListView(APIView):
    """
    Search/list all players.
    GET /api/matches/players/?search=Rohit&role=BAT
    Public — no auth needed.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        players = Player.objects.filter(is_active=True)

        # Optional filters
        search = request.query_params.get('search', '')
        role = request.query_params.get('role', '')

        if search:
            players = players.filter(name__icontains=search)
        if role:
            players = players.filter(role=role.upper())

        players = players.order_by('name')[:50]
        serializer = PlayerSerializer(players, many=True)
        return Response({
            'count': len(players),
            'players': serializer.data
        })


class AdminLockSquadView(APIView):
    """
    Admin locks the squad — no more team editing after this.
    POST /api/matches/<match_id>/lock-squad/
    Admin only.
    """
    permission_classes = [IsAdminUser]

    def post(self, request, match_id):
        match = get_object_or_404(Match, id=match_id)

        if match.squads_locked_at:
            return Response(
                {'error': 'Squad already locked.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        match.squads_locked_at = timezone.now()
        match.save()

        return Response({
            'message': f'Squad locked for {match}.',
            'locked_at': match.squads_locked_at,
        })


class AdminMatchStatusView(APIView):
    """
    Admin updates match status (upcoming → live → completed).
    PATCH /api/matches/<match_id>/status/
    Admin only.
    """
    permission_classes = [IsAdminUser]

    def patch(self, request, match_id):
        match = get_object_or_404(Match, id=match_id)
        new_status = request.data.get('status')

        valid_statuses = ['upcoming', 'live', 'completed', 'cancelled', 'abandoned']
        if new_status not in valid_statuses:
            return Response(
                {'error': f'Invalid status. Choose from: {valid_statuses}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        match.status = new_status
        match.save()

        return Response({
            'message': f'Match status updated to {new_status}.',
            'match_id': str(match.id),
            'status': match.status,
        })