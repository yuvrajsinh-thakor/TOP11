

# Create your models here.
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
import uuid


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_verified', True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Custom user model — email is the login field, not username"""

    ROLE_CHOICES = [
        ('user', 'User'),
        ('admin', 'Admin'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    mobile = models.CharField(max_length=15, blank=True, null=True)
    full_name = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='user')
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)

    # Account status
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)      # Email verified
    is_kyc_done = models.BooleanField(default=False)      # PAN verified (needed for withdrawal)

    # Security
    failed_login_attempts = models.IntegerField(default=0)
    lockout_until = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    device_fingerprint = models.CharField(max_length=256, blank=True)  # For duplicate detection

    # KYC fields
    pan_number = models.CharField(max_length=10, blank=True)
    pan_verified = models.BooleanField(default=False)
    bank_account_number = models.CharField(max_length=20, blank=True)
    bank_ifsc = models.CharField(max_length=11, blank=True)
    bank_name = models.CharField(max_length=100, blank=True)
    upi_id = models.CharField(max_length=100, blank=True)

    # Referral
    referral_code = models.CharField(max_length=12, unique=True, blank=True)
    referred_by = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='referrals'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    objects = UserManager()

    class Meta:
        db_table = 'users'
        verbose_name = 'User'

    def __str__(self):
        return self.email

    def is_locked_out(self):
        if self.lockout_until and self.lockout_until > timezone.now():
            return True
        return False


class OTPVerification(models.Model):
    """Email OTP for registration and password reset"""

    OTP_TYPE_CHOICES = [
        ('registration', 'Registration'),
        ('password_reset', 'Password Reset'),
        ('login', 'Login'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(db_index=True)
    otp = models.CharField(max_length=6)
    otp_type = models.CharField(max_length=20, choices=OTP_TYPE_CHOICES)
    is_used = models.BooleanField(default=False)
    attempts = models.IntegerField(default=0)               # How many wrong guesses
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'otp_verifications'

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"{self.email} - {self.otp_type}"


class Wallet(models.Model):
    """Each user has exactly one wallet with 3 balance buckets"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wallet')

    # The 3 buckets — always stored in paise (1 INR = 100 paise) to avoid float errors
    deposit_balance = models.BigIntegerField(default=0)     # Real money added by user
    winnings_balance = models.BigIntegerField(default=0)    # Money won in contests
    bonus_balance = models.BigIntegerField(default=0)       # Referral/promo (not withdrawable)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'wallets'

    @property
    def total_balance(self):
        return self.deposit_balance + self.winnings_balance + self.bonus_balance

    @property
    def withdrawable_balance(self):
        return self.winnings_balance   # Only winnings can be withdrawn

    def __str__(self):
        return f"Wallet of {self.user.email}"