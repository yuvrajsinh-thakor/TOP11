from django.urls import path
from . import views

urlpatterns = [
    # Public
    path('rules/', views.PointsRulesView.as_view(), name='points-rules'),
    path('<uuid:match_id>/scores/', views.MatchPlayerScoresView.as_view(), name='match-scores'),
    path('my-team/<uuid:team_id>/', views.MyTeamPointsView.as_view(), name='my-team-points'),

    # Admin only
    path('manual-entry/', views.ManualScoreEntryView.as_view(), name='manual-score-entry'),
    path('fetch-live/<uuid:match_id>/', views.FetchLiveScoresView.as_view(), name='fetch-live'),
    path('finish-match/<uuid:match_id>/', views.FinishMatchView.as_view(), name='finish-match'),
]