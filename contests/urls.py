from django.urls import path
from . import views

urlpatterns = [
    # Team creation and management
    path('teams/create/', views.CreateTeamView.as_view(), name='create-team'),
    path('teams/', views.MyTeamsView.as_view(), name='my-teams'),
    path('teams/validate/', views.ValidateTeamView.as_view(), name='validate-team'),
    path('teams/<uuid:team_id>/', views.TeamDetailView.as_view(), name='team-detail'),
    path('teams/<uuid:team_id>/edit/', views.EditTeamView.as_view(), name='edit-team'),
    path('teams/<uuid:team_id>/delete/', views.DeleteTeamView.as_view(), name='delete-team'),

    # Contest listing (public)
    path('', views.ContestListView.as_view(), name='contest-list'),
    path('<uuid:contest_id>/', views.ContestDetailView.as_view(), name='contest-detail'),
    path('<uuid:contest_id>/leaderboard/', views.ContestLeaderboardView.as_view(), name='contest-leaderboard'),

    # Contest actions (auth required)
    path('<uuid:contest_id>/join/', views.JoinContestView.as_view(), name='join-contest'),
    path('<uuid:contest_id>/leave/', views.LeaveContestView.as_view(), name='leave-contest'),
    path('my-contests/', views.MyContestsView.as_view(), name='my-contests'),

    # Admin
    path('admin/create/', views.AdminCreateContestView.as_view(), name='admin-create-contest'),
]