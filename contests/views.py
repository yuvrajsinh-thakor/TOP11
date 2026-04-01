from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.conf import settings

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