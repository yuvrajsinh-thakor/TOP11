from django.urls import path
from . import views

urlpatterns = [
    # Public match listing
    path('upcoming/', views.UpcomingMatchListView.as_view(), name='upcoming-matches'),
    path('live/', views.LiveMatchListView.as_view(), name='live-matches'),
    path('completed/', views.CompletedMatchListView.as_view(), name='completed-matches'),

    # Match detail + squad
    path('<uuid:match_id>/', views.MatchDetailView.as_view(), name='match-detail'),
    path('<uuid:match_id>/players/', views.MatchPlayersView.as_view(), name='match-players'),

    # Player endpoints
    path('players/', views.PlayerListView.as_view(), name='player-list'),
    path('players/<uuid:player_id>/', views.PlayerDetailView.as_view(), name='player-detail'),

    # Admin only
    path('<uuid:match_id>/lock-squad/', views.AdminLockSquadView.as_view(), name='lock-squad'),
    path('<uuid:match_id>/status/', views.AdminMatchStatusView.as_view(), name='match-status'),
]