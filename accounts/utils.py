import random
import string
from django.utils import timezone
from datetime import timedelta
from django.core.mail import send_mail
from django.conf import settings
from .models import OTPVerification


def generate_otp():
    """Generate a secure 6-digit OTP"""
    return ''.join(random.choices(string.digits, k=6))


def generate_referral_code():
    """Generate a unique 8-character referral code"""
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=8))


def create_and_send_otp(email, otp_type):
    """
    Create OTP in DB and send email.
    Deletes any previous unused OTPs for same email+type.
    Returns the OTP object.
    """
    # Delete old OTPs for this email+type
    OTPVerification.objects.filter(
        email=email,
        otp_type=otp_type,
        is_used=False
    ).delete()

    otp_code = generate_otp()
    expiry = timezone.now() + timedelta(minutes=settings.OTP_EXPIRY_MINUTES)

    otp_obj = OTPVerification.objects.create(
        email=email,
        otp=otp_code,
        otp_type=otp_type,
        expires_at=expiry,
    )

    # Send email
    subject_map = {
        'registration': 'Your TOP11 registration OTP',
        'password_reset': 'Your TOP11 password reset OTP',
        'login': 'Your TOP11 login OTP',
    }

    message = f"""
Hi,

Your TOP11 OTP is: {otp_code}

This OTP is valid for {settings.OTP_EXPIRY_MINUTES} minutes.
Do NOT share this OTP with anyone.

If you did not request this, please ignore this email.

- Team TOP11
"""

    try:
        send_mail(
            subject=subject_map.get(otp_type, 'Your TOP11 OTP'),
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )
    except Exception as e:
        # Log error but don't crash — in dev, email prints to console
        print(f"Email send error: {e}")

    return otp_obj


def verify_otp(email, otp_code, otp_type):
    """
    Verify OTP. Returns (True, None) on success or (False, error_message).
    Handles expiry + max attempts automatically.
    """
    try:
        otp_obj = OTPVerification.objects.filter(
            email=email,
            otp_type=otp_type,
            is_used=False,
        ).latest('created_at')
    except OTPVerification.DoesNotExist:
        return False, "No OTP found. Please request a new one."

    if otp_obj.is_expired():
        return False, "OTP has expired. Please request a new one."

    if otp_obj.attempts >= settings.OTP_MAX_ATTEMPTS:
        return False, "Too many wrong attempts. Please request a new OTP."

    if otp_obj.otp != otp_code:
        otp_obj.attempts += 1
        otp_obj.save()
        remaining = settings.OTP_MAX_ATTEMPTS - otp_obj.attempts
        return False, f"Invalid OTP. {remaining} attempt(s) remaining."

    # OTP is correct — mark as used
    otp_obj.is_used = True
    otp_obj.save()

    return True, None


def get_client_ip(request):
    """Extract real IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')