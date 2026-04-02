from rest_framework import serializers
from django.conf import settings
from .models import Transaction, Withdrawal


class WalletSerializer(serializers.Serializer):
    """Current wallet balance breakdown"""
    deposit_balance = serializers.SerializerMethodField()
    winnings_balance = serializers.SerializerMethodField()
    bonus_balance = serializers.SerializerMethodField()
    total_balance = serializers.SerializerMethodField()
    withdrawable_balance = serializers.SerializerMethodField()

    def get_deposit_balance(self, obj):
        return round(obj.deposit_balance / 100, 2)

    def get_winnings_balance(self, obj):
        return round(obj.winnings_balance / 100, 2)

    def get_bonus_balance(self, obj):
        return round(obj.bonus_balance / 100, 2)

    def get_total_balance(self, obj):
        return round(obj.total_balance / 100, 2)

    def get_withdrawable_balance(self, obj):
        return round(obj.withdrawable_balance / 100, 2)


class DepositRequestSerializer(serializers.Serializer):
    """Request to add money to wallet"""
    amount = serializers.DecimalField(max_digits=8, decimal_places=2)

    def validate_amount(self, value):
        if value < 10:
            raise serializers.ValidationError("Minimum deposit is ₹10.")
        if value > 100000:
            raise serializers.ValidationError("Maximum deposit is ₹1,00,000 per transaction.")
        return value


class WithdrawalRequestSerializer(serializers.Serializer):
    """Request to withdraw money"""
    amount = serializers.DecimalField(max_digits=8, decimal_places=2)
    withdrawal_method = serializers.ChoiceField(
        choices=[('upi', 'UPI'), ('bank', 'Bank Transfer')]
    )

    def validate_amount(self, value):
        min_withdrawal = settings.TOP11_MIN_WITHDRAWAL
        if value < min_withdrawal:
            raise serializers.ValidationError(
                f"Minimum withdrawal is ₹{min_withdrawal}."
            )
        if value > 200000:
            raise serializers.ValidationError("Maximum withdrawal is ₹2,00,000 per request.")
        return value

    def validate(self, data):
        user = self.context['request'].user
        amount_paise = int(data['amount'] * 100)

        # KYC check
        if not user.is_kyc_done:
            raise serializers.ValidationError(
                {'kyc': 'KYC verification required before withdrawal. Please submit your PAN card details.'}
            )

        # Check withdrawal method has details
        if data['withdrawal_method'] == 'upi' and not user.upi_id:
            raise serializers.ValidationError(
                {'upi': 'Please add your UPI ID in profile settings first.'}
            )
        if data['withdrawal_method'] == 'bank':
            if not user.bank_account_number or not user.bank_ifsc:
                raise serializers.ValidationError(
                    {'bank': 'Please add your bank account details in profile settings first.'}
                )

        # Check sufficient winnings balance
        try:
            wallet = user.wallet
        except Exception:
            raise serializers.ValidationError({'wallet': 'Wallet not found.'})

        if wallet.winnings_balance < amount_paise:
            raise serializers.ValidationError(
                {'amount': f'Insufficient winnings balance. '
                           f'Available: ₹{wallet.winnings_balance/100:.2f}'}
            )

        # Check no pending withdrawal already
        if Withdrawal.objects.filter(
            user=user, status__in=['pending', 'processing']
        ).exists():
            raise serializers.ValidationError(
                {'withdrawal': 'You already have a pending withdrawal request.'}
            )

        return data


class TransactionSerializer(serializers.ModelSerializer):
    amount_inr = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = [
            'id', 'transaction_type', 'status',
            'amount_inr', 'wallet_bucket',
            'description', 'created_at',
        ]

    def get_amount_inr(self, obj):
        return round(obj.amount / 100, 2)


class WithdrawalSerializer(serializers.ModelSerializer):
    amount_inr = serializers.SerializerMethodField()

    class Meta:
        model = Withdrawal
        fields = [
            'id', 'amount_inr', 'status',
            'bank_account', 'upi_id',
            'rejection_reason', 'created_at',
        ]

    def get_amount_inr(self, obj):
        return round(obj.amount / 100, 2)


class KYCSerializer(serializers.Serializer):
    """Submit KYC details"""
    pan_number = serializers.CharField(min_length=10, max_length=10)
    bank_account_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    bank_ifsc = serializers.CharField(max_length=11, required=False, allow_blank=True)
    bank_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    upi_id = serializers.CharField(max_length=100, required=False, allow_blank=True)

    def validate_pan_number(self, value):
        import re
        value = value.upper().strip()
        # PAN format: 5 letters + 4 digits + 1 letter (e.g. ABCDE1234F)
        if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$', value):
            raise serializers.ValidationError(
                "Invalid PAN format. Example: ABCDE1234F"
            )
        return value

    def validate(self, data):
        # User must have at least one withdrawal method
        has_bank = data.get('bank_account_number') and data.get('bank_ifsc')
        has_upi = data.get('upi_id')
        if not has_bank and not has_upi:
            raise serializers.ValidationError(
                "Please provide either bank account details or UPI ID."
            )
        return data