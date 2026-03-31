from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from .models import Wallet

User = get_user_model()


class RegisterRequestSerializer(serializers.Serializer):
    """Step 1 of registration — just the email"""
    email = serializers.EmailField()

    def validate_email(self, value):
        value = value.lower().strip()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value


class VerifyOTPAndCreateUserSerializer(serializers.Serializer):
    """Step 2 of registration — OTP + set password"""
    email = serializers.EmailField()
    otp = serializers.CharField(min_length=6, max_length=6)
    password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)
    full_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate(self, data):
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return data


class LoginSerializer(serializers.Serializer):
    """Login with email + password"""
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate_email(self, value):
        return value.lower().strip()


class ForgotPasswordSerializer(serializers.Serializer):
    """Request a password reset OTP"""
    email = serializers.EmailField()

    def validate_email(self, value):
        value = value.lower().strip()
        if not User.objects.filter(email=value, is_active=True).exists():
            # Don't reveal whether email exists — security best practice
            # We still return success to the user
            pass
        return value


class VerifyResetOTPSerializer(serializers.Serializer):
    """Verify reset OTP"""
    email = serializers.EmailField()
    otp = serializers.CharField(min_length=6, max_length=6)


class ResetPasswordSerializer(serializers.Serializer):
    """Set new password after OTP verified"""
    email = serializers.EmailField()
    otp = serializers.CharField(min_length=6, max_length=6)
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        validate_password(value)
        return value

    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return data


class WalletSerializer(serializers.ModelSerializer):
    total_balance_inr = serializers.SerializerMethodField()
    deposit_balance_inr = serializers.SerializerMethodField()
    winnings_balance_inr = serializers.SerializerMethodField()
    bonus_balance_inr = serializers.SerializerMethodField()

    class Meta:
        model = Wallet
        fields = [
            'deposit_balance_inr',
            'winnings_balance_inr',
            'bonus_balance_inr',
            'total_balance_inr',
        ]

    def get_total_balance_inr(self, obj):
        return round(obj.total_balance / 100, 2)

    def get_deposit_balance_inr(self, obj):
        return round(obj.deposit_balance / 100, 2)

    def get_winnings_balance_inr(self, obj):
        return round(obj.winnings_balance / 100, 2)

    def get_bonus_balance_inr(self, obj):
        return round(obj.bonus_balance / 100, 2)


class UserProfileSerializer(serializers.ModelSerializer):
    wallet = WalletSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'email', 'full_name', 'mobile',
            'is_verified', 'is_kyc_done',
            'referral_code', 'wallet',
            'created_at',
        ]
        read_only_fields = ['id', 'email', 'is_verified', 'is_kyc_done', 'referral_code', 'created_at']


class UpdateProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['full_name', 'mobile']

    def validate_mobile(self, value):
        if value and not value.isdigit():
            raise serializers.ValidationError("Mobile number must contain only digits.")
        if value and len(value) not in [10, 12]:
            raise serializers.ValidationError("Enter a valid 10 or 12 digit mobile number.")
        return value


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        validate_password(value)
        return value

    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return data