from django.urls import re_path
from scoring import consumers

websocket_urlpatterns = [
    # Live player scores for a match
    re_path(
        r'ws/match/(?P<match_id>[0-9a-f-]+)/scores/$',
        consumers.MatchScoreConsumer.as_asgi(),
    ),
    # Live leaderboard for a contest
    re_path(
        r'ws/contest/(?P<contest_id>[0-9a-f-]+)/leaderboard/$',
        consumers.ContestLeaderboardConsumer.as_asgi(),
    ),
    # Match status updates
    re_path(
        r'ws/match/(?P<match_id>[0-9a-f-]+)/status/$',
        consumers.MatchStatusConsumer.as_asgi(),
    ),
]