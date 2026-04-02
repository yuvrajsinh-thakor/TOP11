from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone


def broadcast_score_update(match_id, player_id, player_name,
                           total_points, breakdown):
    """
    Push a single player's score update to all WebSocket
    clients watching that match.
    Call this after save_player_score().
    """
    channel_layer = get_channel_layer()
    if not channel_layer:
        return

    async_to_sync(channel_layer.group_send)(
        f'match_scores_{match_id}',
        {
            'type': 'score_update',
            'player_id': str(player_id),
            'player_name': player_name,
            'total_points': float(total_points),
            'breakdown': breakdown,
            'timestamp': timezone.now().isoformat(),
        }
    )


def broadcast_all_scores(match_id, scores_data):
    """
    Push all player scores at once to all clients.
    Call this after update_all_team_points().
    """
    channel_layer = get_channel_layer()
    if not channel_layer:
        return

    async_to_sync(channel_layer.group_send)(
        f'match_scores_{match_id}',
        {
            'type': 'all_scores_update',
            'scores': scores_data,
            'timestamp': timezone.now().isoformat(),
        }
    )


def broadcast_leaderboard_update(contest_id, leaderboard_data, total_entries):
    """
    Push leaderboard update to all clients watching a contest.
    Call this after rebuild_leaderboard().
    """
    channel_layer = get_channel_layer()
    if not channel_layer:
        return

    async_to_sync(channel_layer.group_send)(
        f'leaderboard_{contest_id}',
        {
            'type': 'leaderboard_update',
            'leaderboard': leaderboard_data,
            'total_entries': total_entries,
            'timestamp': timezone.now().isoformat(),
        }
    )


def broadcast_match_status(match_id, new_status, message=''):
    """
    Push match status change to all connected clients.
    Call this when match goes live or completes.
    """
    channel_layer = get_channel_layer()
    if not channel_layer:
        return

    async_to_sync(channel_layer.group_send)(
        f'match_status_{match_id}',
        {
            'type': 'match_status_update',
            'status': new_status,
            'message': message,
            'timestamp': timezone.now().isoformat(),
        }
    )