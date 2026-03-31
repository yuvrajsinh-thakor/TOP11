from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from .models import Wallet
from .serializers import (
    RegisterRequestSerializer,
    VerifyOTPAndCreateUserSerializer,
    LoginSerializer,
    ForgotPasswordSerializer,
    ResetPasswordSerializer,
    VerifyResetOTPSerializer,
    UserProfileSerializer,
    UpdateProfileSerializer,
    ChangePasswordSerializer,
)
from .utils import create_and_send_otp, verify_otp, generate_referral_code, get_client_ip

User = get_user_model()


def get_tokens_for_user(user):
    """Generate JWT access + refresh tokens for a user"""
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


class RegisterRequestView(APIView):
    """
    Step 1: User submits email → OTP sent to their email.
    POST /api/auth/register/
    Body: { "email": "user@example.com" }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email']
        create_and_send_otp(email, 'registration')

        return Response({
            'message': f'OTP sent to {email}. Valid for 5 minutes.',
            'email': email,
        }, status=status.HTTP_200_OK)


class VerifyOTPAndRegisterView(APIView):
    """
    Step 2: User submits OTP + password → account created.
    POST /api/auth/verify-registration/
    Body: { "email": "...", "otp": "123456", "password": "...", "confirm_password": "...", "full_name": "..." }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyOTPAndCreateUserSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        email = data['email'].lower().strip()

        # Double-check email not already registered (race condition guard)
        if User.objects.filter(email=email).exists():
            return Response(
                {'error': 'An account with this email already exists.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verify OTP
        success, error_msg = verify_otp(email, data['otp'], 'registration')
        if not success:
            return Response({'error': error_msg}, status=status.HTTP_400_BAD_REQUEST)

        # Create user
        referral_code = generate_referral_code()
        # Ensure referral code is unique
        while User.objects.filter(referral_code=referral_code).exists():
            referral_code = generate_referral_code()

        user = User.objects.create_user(
            email=email,
            password=data['password'],
            full_name=data.get('full_name', ''),
            is_verified=True,
            referral_code=referral_code,
            last_login_ip=get_client_ip(request),
        )

        # Wallet is auto-created by signal (see signals.py)

        # Return JWT tokens immediately so user is logged in
        tokens = get_tokens_for_user(user)

        return Response({
            'message': 'Account created successfully!',
            'user': {
                'id': str(user.id),
                'email': user.email,
                'full_name': user.full_name,
                'referral_code': user.referral_code,
            },
            'tokens': tokens,
        }, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    """
    Login with email + password → JWT tokens.
    POST /api/auth/login/
    Body: { "email": "...", "password": "..." }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email']
        password = serializer.validated_data['password']

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {'error': 'Invalid email or password.'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Check account lockout
        if user.is_locked_out():
            return Response(
                {'error': 'Account temporarily locked due to too many failed attempts. Try again in 15 minutes.'},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        # Check account is active
        if not user.is_active:
            return Response(
                {'error': 'Your account has been deactivated. Please contact support.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Check email is verified
        if not user.is_verified:
            return Response(
                {'error': 'Please verify your email before logging in.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Verify password
        if not user.check_password(password):
            # Increment failed attempts
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 5:
                # Lock account for 15 minutes
                user.lockout_until = timezone.now() + timedelta(minutes=15)
            user.save()

            return Response(
                {'error': 'Invalid email or password.'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Success — reset failed attempts
        user.failed_login_attempts = 0
        user.lockout_until = None
        user.last_login_ip = get_client_ip(request)
        user.save()

        tokens = get_tokens_for_user(user)

        return Response({
            'message': 'Login successful.',
            'user': {
                'id': str(user.id),
                'email': user.email,
                'full_name': user.full_name,
            },
            'tokens': tokens,
        }, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """
    Logout — blacklist the refresh token so it can't be reused.
    POST /api/auth/logout/
    Header: Authorization: Bearer <access_token>
    Body: { "refresh": "<refresh_token>" }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response(
                {'error': 'Refresh token is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            return Response(
                {'error': 'Invalid or already expired token.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response({'message': 'Logged out successfully.'}, status=status.HTTP_200_OK)


class ForgotPasswordView(APIView):
    """
    Request password reset OTP.
    POST /api/auth/forgot-password/
    Body: { "email": "..." }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email'].lower().strip()

        # Always send same response — don't reveal if email exists
        if User.objects.filter(email=email, is_active=True).exists():
            create_and_send_otp(email, 'password_reset')

        return Response({
            'message': 'If this email is registered, an OTP has been sent.',
        }, status=status.HTTP_200_OK)


class VerifyResetOTPView(APIView):
    """
    Verify the reset OTP (without setting new password yet).
    POST /api/auth/verify-reset-otp/
    Body: { "email": "...", "otp": "123456" }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyResetOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email'].lower().strip()
        otp_code = serializer.validated_data['otp']

        success, error_msg = verify_otp(email, otp_code, 'password_reset')
        if not success:
            return Response({'error': error_msg}, status=status.HTTP_400_BAD_REQUEST)

        # Re-create a "used" marker OTP so reset-password step can verify chain
        # We do this by sending a second OTP of type password_reset that's pre-verified
        # Simpler: just verify OTP inline in reset-password view

        return Response({'message': 'OTP verified. You can now set a new password.'}, status=status.HTTP_200_OK)


class ResetPasswordView(APIView):
    """
    Set new password (OTP verified again for security).
    POST /api/auth/reset-password/
    Body: { "email": "...", "otp": "123456", "new_password": "...", "confirm_password": "..." }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        email = data['email'].lower().strip()

        # Verify OTP one final time
        success, error_msg = verify_otp(email, data['otp'], 'password_reset')
        if not success:
            return Response({'error': error_msg}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email, is_active=True)
        except User.DoesNotExist:
            return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

        user.set_password(data['new_password'])
        user.failed_login_attempts = 0
        user.lockout_until = None
        user.save()

        return Response({'message': 'Password reset successfully. Please log in.'}, status=status.HTTP_200_OK)


class ProfileView(APIView):
    """
    Get logged-in user's profile + wallet balance.
    GET /api/auth/profile/
    Header: Authorization: Bearer <access_token>
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request):
        """Update profile (name, mobile)"""
        serializer = UpdateProfileSerializer(request.user, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response({
            'message': 'Profile updated.',
            'user': UserProfileSerializer(request.user).data
        }, status=status.HTTP_200_OK)


class ChangePasswordView(APIView):
    """
    Change password while logged in.
    POST /api/auth/change-password/
    Header: Authorization: Bearer <access_token>
    Body: { "old_password": "...", "new_password": "...", "confirm_password": "..." }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        if not user.check_password(serializer.validated_data['old_password']):
            return Response(
                {'error': 'Current password is incorrect.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(serializer.validated_data['new_password'])
        user.save()

        return Response({'message': 'Password changed successfully. Please log in again.'}, status=status.HTTP_200_OK)