import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone


class MatchScoreConsumer(AsyncWebsocketConsumer):
    """
    WebSocket for live player scores in a match.
    Connect: ws://localhost:8000/ws/match/<match_id>/scores/

    Broadcasts to all viewers of the same match when
    any player's score is updated.
    """

    async def connect(self):
        self.match_id = self.scope['url_route']['kwargs']['match_id']
        self.group_name = f'match_scores_{self.match_id}'

        # Join the group for this match
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()

        # Send current scores immediately on connect
        scores = await self.get_current_scores()
        await self.send(text_data=json.dumps({
            'type': 'initial_scores',
            'match_id': self.match_id,
            'scores': scores,
            'timestamp': timezone.now().isoformat(),
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        """Handle messages from browser (ping/pong keepalive)"""
        try:
            data = json.loads(text_data)
            if data.get('type') == 'ping':
                await self.send(text_data=json.dumps({'type': 'pong'}))
        except json.JSONDecodeError:
            pass

    async def score_update(self, event):
        """
        Called when a score update is broadcast to this group.
        Forwards the update to the WebSocket client.
        """
        await self.send(text_data=json.dumps({
            'type': 'score_update',
            'player_id': event['player_id'],
            'player_name': event['player_name'],
            'total_points': event['total_points'],
            'breakdown': event['breakdown'],
            'timestamp': event['timestamp'],
        }))

    async def all_scores_update(self, event):
        """Called when full scores refresh is broadcast"""
        await self.send(text_data=json.dumps({
            'type': 'all_scores',
            'scores': event['scores'],
            'timestamp': event['timestamp'],
        }))

    @database_sync_to_async
    def get_current_scores(self):
        from scoring.models import PlayerMatchScore
        scores = PlayerMatchScore.objects.filter(
            match_id=self.match_id
        ).select_related('player').order_by('-total_fantasy_points')

        return [{
            'player_id': str(s.player_id),
            'player_name': s.player.name,
            'role': s.player.role,
            'runs_scored': s.runs_scored,
            'wickets_taken': s.wickets_taken,
            'catches': s.catches,
            'total_points': float(s.total_fantasy_points),
            'breakdown': s.points_breakdown,
        } for s in scores]


class ContestLeaderboardConsumer(AsyncWebsocketConsumer):
    """
    WebSocket for live contest leaderboard.
    Connect: ws://localhost:8000/ws/contest/<contest_id>/leaderboard/

    Sends top 10 + the connecting user's own rank.
    Updates every time leaderboard is rebuilt.
    """

    async def connect(self):
        self.contest_id = self.scope['url_route']['kwargs']['contest_id']
        self.group_name = f'leaderboard_{self.contest_id}'

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()

        # Send current leaderboard immediately
        leaderboard = await self.get_leaderboard()
        await self.send(text_data=json.dumps({
            'type': 'initial_leaderboard',
            'contest_id': self.contest_id,
            'leaderboard': leaderboard,
            'timestamp': timezone.now().isoformat(),
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            if data.get('type') == 'ping':
                await self.send(text_data=json.dumps({'type': 'pong'}))
        except json.JSONDecodeError:
            pass

    async def leaderboard_update(self, event):
        """Called when leaderboard is rebuilt"""
        await self.send(text_data=json.dumps({
            'type': 'leaderboard_update',
            'leaderboard': event['leaderboard'],
            'total_entries': event['total_entries'],
            'timestamp': event['timestamp'],
        }))

    @database_sync_to_async
    def get_leaderboard(self):
        from scoring.models import Leaderboard
        rankings = Leaderboard.objects.filter(
            contest_id=self.contest_id
        ).select_related('user', 'team').order_by('rank')[:50]

        return [{
            'rank': r.rank,
            'user': r.user.full_name or r.user.email.split('@')[0],
            'team_name': r.team.name,
            'points': float(r.total_points),
            'prize_inr': round(r.prize_amount / 100, 2),
        } for r in rankings]


class MatchStatusConsumer(AsyncWebsocketConsumer):
    """
    WebSocket for match status changes.
    Connect: ws://localhost:8000/ws/match/<match_id>/status/

    Notifies clients when match goes from upcoming → live → completed.
    """

    async def connect(self):
        self.match_id = self.scope['url_route']['kwargs']['match_id']
        self.group_name = f'match_status_{self.match_id}'

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()

        # Send current status immediately
        match_info = await self.get_match_status()
        await self.send(text_data=json.dumps({
            'type': 'initial_status',
            'match_id': self.match_id,
            **match_info,
            'timestamp': timezone.now().isoformat(),
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            if data.get('type') == 'ping':
                await self.send(text_data=json.dumps({'type': 'pong'}))
        except json.JSONDecodeError:
            pass

    async def match_status_update(self, event):
        """Called when match status changes"""
        await self.send(text_data=json.dumps({
            'type': 'status_update',
            'status': event['status'],
            'message': event.get('message', ''),
            'timestamp': event['timestamp'],
        }))

    @database_sync_to_async
    def get_match_status(self):
        from matches.models import Match
        try:
            match = Match.objects.select_related(
                'team_a', 'team_b'
            ).get(id=self.match_id)
            return {
                'status': match.status,
                'team_a': match.team_a.short_name,
                'team_b': match.team_b.short_name,
                'scheduled_at': match.scheduled_at.isoformat(),
            }
        except Match.DoesNotExist:
            return {'status': 'not_found'}