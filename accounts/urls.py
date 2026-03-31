from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    # Registration (2 steps)
    path('register/', views.RegisterRequestView.as_view(), name='register'),
    path('verify-registration/', views.VerifyOTPAndRegisterView.as_view(), name='verify-registration'),

    # Login / Logout
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),

    # JWT token refresh (built-in view from simplejwt)
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),

    # Password reset (2 steps)
    path('forgot-password/', views.ForgotPasswordView.as_view(), name='forgot-password'),
    path('verify-reset-otp/', views.VerifyResetOTPView.as_view(), name='verify-reset-otp'),
    path('reset-password/', views.ResetPasswordView.as_view(), name='reset-password'),

    # Profile (protected)
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('change-password/', views.ChangePasswordView.as_view(), name='change-password'),
]