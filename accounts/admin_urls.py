from django.urls import path
from . import admin_views

urlpatterns = [
    path('dashboard/', admin_views.DashboardStatsView.as_view(), name='admin-dashboard'),
    path('kyc/', admin_views.KYCApproveView.as_view(), name='admin-kyc'),
    path('ban-user/', admin_views.BanUserView.as_view(), name='admin-ban-user'),
    path('users/', admin_views.PlatformUsersListView.as_view(), name='admin-users'),
    path('users/<uuid:user_id>/', admin_views.UserDetailAdminView.as_view(), name='admin-user-detail'),
]