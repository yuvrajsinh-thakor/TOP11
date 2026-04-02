from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from django.shortcuts import get_object_or_404

from .models import PlayerMatchScore, PointsRule, Leaderboard
from .points_engine import (
    get_points_rules,
    save_player_score,
    update_all_team_points,
    rebuild_leaderboard,
    distribute_prizes,
    cancel_contest_and_refund,
)
from .cricapi import get_match_scorecard, parse_player_stats_from_scorecard
from matches.models import Match, Player, Squad
from contests.models import Contest


class MatchPlayerScoresView(APIView):
    """
    Get all player fantasy points for a match.
    GET /api/scoring/<match_id>/scores/
    Public.
    """
    permission_classes = [AllowAny]

    def get(self, request, match_id):
        match = get_object_or_404(Match, id=match_id)
        scores = PlayerMatchScore.objects.filter(
            match=match
        ).select_related('player').order_by('-total_fantasy_points')

        data = [{
            'player_id': str(s.player_id),
            'player_name': s.player.name,
            'role': s.player.role,
            'runs_scored': s.runs_scored,
            'fours': s.fours,
            'sixes': s.sixes,
            'wickets_taken': s.wickets_taken,
            'catches': s.catches,
            'stumpings': s.stumpings,
            'maiden_overs': s.maiden_overs,
            'total_fantasy_points': float(s.total_fantasy_points),
            'points_breakdown': s.points_breakdown,
        } for s in scores]

        return Response({
            'match': str(match),
            'status': match.status,
            'player_count': len(data),
            'scores': data,
        })


class ManualScoreEntryView(APIView):
    """
    Admin manually enters player stats (when CricAPI not available).
    POST /api/scoring/manual-entry/
    Admin only.

    Body:
    {
        "match_id": "uuid",
        "players": [
            {
                "player_id": "uuid",
                "runs_scored": 45,
                "fours": 4,
                "sixes": 2,
                "is_out": true,
                "wickets_taken": 0,
                "maiden_overs": 0,
                "catches": 1,
                "stumpings": 0,
                "run_outs_direct": 0,
                "run_outs_indirect": 0
            },
            ...
        ]
    }
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        match_id = request.data.get('match_id')
        players_data = request.data.get('players', [])

        if not match_id or not players_data:
            return Response(
                {'error': 'match_id and players list are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        match = get_object_or_404(Match, id=match_id)
        rules = get_points_rules()

        if not rules:
            return Response(
                {'error': 'No points rules found. Run seed_points_rules first.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        results = []
        errors = []

        for player_data in players_data:
            player_id = player_data.get('player_id')
            try:
                player = Player.objects.get(id=player_id)
            except Player.DoesNotExist:
                errors.append(f'Player {player_id} not found.')
                continue

            # Verify player is in this match
            if not Squad.objects.filter(match=match, player=player).exists():
                errors.append(f'{player.name} is not in this match squad.')
                continue

            score = save_player_score(match, player, player_data, rules)
            results.append({
                'player': player.name,
                'total_fantasy_points': float(score.total_fantasy_points),
                'breakdown': score.points_breakdown,
            })

        # Update all team totals for this match
        if results:
            update_all_team_points(match)

            # Rebuild leaderboard for all contests in this match
            for contest in Contest.objects.filter(match=match):
                rebuild_leaderboard(contest)

        return Response({
            'message': f'Scores saved for {len(results)} players.',
            'results': results,
            'errors': errors,
        })


class FetchLiveScoresView(APIView):
    """
    Fetch live scores from CricAPI and auto-calculate points.
    POST /api/scoring/fetch-live/<match_id>/
    Admin only.
    """
    permission_classes = [IsAdminUser]

    def post(self, request, match_id):
        match = get_object_or_404(Match, id=match_id)

        if not match.cricapi_match_id:
            return Response(
                {'error': 'No CricAPI match ID set for this match. '
                          'Add it in Admin → Matches → cricapi_match_id field.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Fetch from CricAPI
        scorecard = get_match_scorecard(match.cricapi_match_id)
        if not scorecard:
            return Response(
                {'error': 'Failed to fetch scorecard from CricAPI. Check your API key.'},
                status=status.HTTP_502_BAD_GATEWAY
            )

        # Parse player stats
        player_stats = parse_player_stats_from_scorecard(scorecard)
        if not player_stats:
            return Response(
                {'error': 'No player stats found in scorecard.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        rules = get_points_rules()
        results = []
        not_found = []

        # Match parsed stats to DB players by name
        squad_players = Squad.objects.filter(
            match=match
        ).select_related('player')

        for squad in squad_players:
            player = squad.player
            # Try exact match first, then partial
            stats = player_stats.get(player.name)
            if not stats:
                # Try partial name match
                for api_name, api_stats in player_stats.items():
                    if player.name.lower() in api_name.lower() or \
                       api_name.lower() in player.name.lower():
                        stats = api_stats
                        break

            if stats:
                score = save_player_score(match, player, stats, rules)
                results.append({
                    'player': player.name,
                    'points': float(score.total_fantasy_points),
                })
            else:
                not_found.append(player.name)

        # Update all team totals
        if results:
            update_all_team_points(match)
            for contest in Contest.objects.filter(match=match):
                rebuild_leaderboard(contest)

        return Response({
            'message': f'Live scores fetched. {len(results)} players updated.',
            'updated': results,
            'not_matched': not_found,
        })


class FinishMatchView(APIView):
    """
    Admin marks match as complete and distributes prizes.
    POST /api/scoring/finish-match/<match_id>/
    Admin only.
    """
    permission_classes = [IsAdminUser]

    def post(self, request, match_id):
        match = get_object_or_404(Match, id=match_id)

        if match.status == 'completed':
            return Response({'error': 'Match already completed.'}, status=400)

        # Mark match as completed
        match.status = 'completed'
        match.save()

        # Broadcast match status change
        from scoring.broadcast import broadcast_match_status
        try:
            broadcast_match_status(
                str(match.id), 'completed',
                'Match has ended. Final scores are in!'
            )
        except Exception:
            pass


        # Lock all teams
        from contests.models import UserTeam
        UserTeam.objects.filter(match=match).update(is_locked=True)

        # Final leaderboard rebuild
        contest_results = []
        for contest in Contest.objects.filter(match=match, status='upcoming'):
            # Check minimum entries
            if contest.current_entries < contest.min_entries:
                result = cancel_contest_and_refund(contest)
                contest_results.append({
                    'contest': contest.name,
                    'action': 'cancelled_and_refunded',
                    **result,
                })
            else:
                rebuild_leaderboard(contest)
                contest.status = 'live'
                contest.save()
                result = distribute_prizes(contest)
                contest_results.append({
                    'contest': contest.name,
                    'action': 'prizes_distributed',
                    **result,
                })

        return Response({
            'message': f'Match {match} marked as completed.',
            'contests_processed': contest_results,
        })


class PointsRulesView(APIView):
    """
    View all active scoring rules.
    GET /api/scoring/rules/
    Public.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        rules = PointsRule.objects.filter(
            is_active=True
        ).order_by('sport', 'event_name')

        data = [{
            'event_name': r.event_name,
            'event_code': r.event_code,
            'points': float(r.points),
            'description': r.description,
        } for r in rules]

        return Response({
            'count': len(data),
            'rules': data,
        })


class MyTeamPointsView(APIView):
    """
    Get points breakdown for a user's specific team.
    GET /api/scoring/my-team/<team_id>/
    Auth required.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, team_id):
        from contests.models import UserTeam, UserTeamPlayer

        team = get_object_or_404(
            UserTeam,
            id=team_id,
            user=request.user
        )

        players_data = []
        team_players = UserTeamPlayer.objects.filter(
            team=team
        ).select_related('player')

        for tp in team_players:
            role = 'normal'
            if tp.multiplier == 2:
                role = 'captain'
            elif tp.multiplier == Decimal('1.5'):
                role = 'vice_captain'

            players_data.append({
                'player_name': tp.player.name,
                'player_role': tp.player.role,
                'selection_role': role,
                'multiplier': float(tp.multiplier),
                'raw_points': float(tp.raw_points),
                'final_points': float(tp.final_points),
            })

        players_data.sort(key=lambda x: x['final_points'], reverse=True)

        return Response({
            'team_name': team.name,
            'total_points': float(team.total_points),
            'is_locked': team.is_locked,
            'players': players_data,
        })


# Fix missing import
from decimal import Decimal