from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db import transaction as db_transaction
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.conf import settings
from django.utils import timezone
import json
import uuid
from accounts.models import Wallet
from .models import Transaction, Withdrawal
from .serializers import (
    WalletSerializer,
    DepositRequestSerializer,
    WithdrawalRequestSerializer,
    TransactionSerializer,
    WithdrawalSerializer,
    KYCSerializer,
)
from .cashfree import (
    create_payment_order,
    verify_webhook_signature,
    verify_payment_order,
    initiate_payout,
)
from accounts.models import Wallet


class WalletView(APIView):
    """
    Get wallet balance.
    GET /api/payments/wallet/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wallet = request.user.wallet
        serializer = WalletSerializer(wallet)
        return Response(serializer.data)


class DepositView(APIView):
    """
    Step 1 of adding money: Create Cashfree order.
    POST /api/payments/deposit/
    Body: { "amount": 100 }

    Returns payment_session_id which frontend uses to
    open Cashfree payment popup.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = DepositRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        amount_inr = serializer.validated_data['amount']
        user = request.user

        # Create Cashfree order
        order_id, payment_session_id, error = create_payment_order(
            user=user,
            amount_inr=float(amount_inr),
        )

        if error:
            return Response(
                {'error': f'Payment gateway error: {error}'},
                status=status.HTTP_502_BAD_GATEWAY
            )

        # Save pending transaction
        Transaction.objects.create(
            user=user,
            transaction_type='deposit',
            status='pending',
            amount=int(amount_inr * 100),   # Store in paise
            wallet_bucket='deposit',
            cashfree_order_id=order_id,
            description=f'Wallet deposit ₹{amount_inr}',
            idempotency_key=order_id,
        )

        return Response({
            'order_id': order_id,
            'payment_session_id': payment_session_id,
            'amount': float(amount_inr),
            'message': 'Order created. Use payment_session_id to open payment UI.',
        }, status=status.HTTP_201_CREATED)


class VerifyDepositView(APIView):
    """
    Manually verify a payment (fallback if webhook missed).
    POST /api/payments/verify-deposit/
    Body: { "order_id": "TOP11_xxx" }
    """
    permission_classes = [IsAuthenticated]

    @db_transaction.atomic
    def post(self, request):
        order_id = request.data.get('order_id')
        if not order_id:
            return Response({'error': 'order_id is required.'}, status=400)

        # Find the transaction
        try:
            txn = Transaction.objects.get(
                cashfree_order_id=order_id,
                user=request.user,
                transaction_type='deposit',
            )
        except Transaction.DoesNotExist:
            return Response({'error': 'Transaction not found.'}, status=404)

        if txn.status == 'success':
            return Response({'message': 'Payment already processed.', 'status': 'success'})

        # Verify with Cashfree
        cf_status, cf_amount, error = verify_payment_order(order_id)

        if error:
            return Response({'error': error}, status=502)

        if cf_status == 'PAID':
            # Credit wallet
            wallet = request.user.wallet
            wallet.deposit_balance += txn.amount
            wallet.save()

            txn.status = 'success'
            txn.save()

            return Response({
                'message': 'Payment verified. Wallet credited.',
                'amount_credited': round(txn.amount / 100, 2),
                'new_balance': round(wallet.deposit_balance / 100, 2),
            })

        return Response({
            'message': 'Payment not completed yet.',
            'cashfree_status': cf_status,
        })


@method_decorator(csrf_exempt, name='dispatch')
class CashfreeWebhookView(APIView):
    """
    Cashfree calls this URL when payment is completed.
    POST /api/payments/webhook/cashfree/
    Public — Cashfree server calls this, not the user.

    SECURITY: We verify the signature before doing anything.
    """
    permission_classes = [AllowAny]

    @db_transaction.atomic
    def post(self, request):
        # Get signature from headers
        signature = request.headers.get('x-webhook-signature')
        timestamp = request.headers.get('x-webhook-timestamp')

        if not signature or not timestamp:
            return Response(
                {'error': 'Missing signature headers'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get raw body for signature verification
        raw_body = request.body.decode('utf-8')

        # CRITICAL: Verify signature before processing anything
        if not verify_webhook_signature(raw_body, timestamp, signature):
            return Response(
                {'error': 'Invalid signature'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Parse the webhook payload
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            return Response({'error': 'Invalid JSON'}, status=400)

        event_type = payload.get('type', '')
        data = payload.get('data', {})

        # Handle payment success
        if event_type == 'PAYMENT_SUCCESS_WEBHOOK':
            return self._handle_payment_success(data)

        # Handle payout (withdrawal) events
        if event_type in ['TRANSFER_SUCCESS', 'TRANSFER_FAILED']:
            return self._handle_payout_event(event_type, data)

        # Unknown event — just acknowledge
        return Response({'status': 'ok'})

    def _handle_payment_success(self, data):
        order_id = data.get('order', {}).get('order_id', '')
        amount_paid = data.get('payment', {}).get('payment_amount', 0)
        payment_id = data.get('payment', {}).get('cf_payment_id', '')

        if not order_id:
            return Response({'error': 'No order_id in webhook'}, status=400)

        # Find the pending transaction
        try:
            txn = Transaction.objects.select_for_update().get(
                cashfree_order_id=order_id,
                transaction_type='deposit',
                status='pending',
            )
        except Transaction.DoesNotExist:
            # Already processed or doesn't exist — return 200 to stop retries
            return Response({'status': 'already_processed'})

        # Verify amount matches
        expected_paise = txn.amount
        paid_paise = int(float(amount_paid) * 100)

        if paid_paise < expected_paise:
            txn.status = 'failed'
            txn.save()
            return Response({'error': 'Amount mismatch'}, status=400)

        # Credit the wallet
        wallet = txn.user.wallet
        wallet.deposit_balance += txn.amount
        wallet.save()

        # Update transaction
        txn.status = 'success'
        txn.cashfree_payment_id = str(payment_id)
        txn.save()

        return Response({'status': 'ok'})

    def _handle_payout_event(self, event_type, data):
        transfer_id = data.get('transfer_id', '')

        try:
            withdrawal = Withdrawal.objects.select_for_update().get(
                cashfree_transfer_id=transfer_id
            )
        except Withdrawal.DoesNotExist:
            return Response({'status': 'ok'})

        if event_type == 'TRANSFER_SUCCESS':
            withdrawal.status = 'success'
        else:
            withdrawal.status = 'failed'
            withdrawal.rejection_reason = data.get('reason', 'Transfer failed')

            # Refund the amount back to winnings
            wallet = withdrawal.user.wallet
            wallet.winnings_balance += withdrawal.amount
            wallet.save()

            Transaction.objects.create(
                user=withdrawal.user,
                transaction_type='refund',
                status='success',
                amount=withdrawal.amount,
                wallet_bucket='winnings',
                description=f'Refund: withdrawal failed - {withdrawal.rejection_reason}',
                idempotency_key=f'withdrawal_refund_{withdrawal.id}',
            )

        withdrawal.save()
        return Response({'status': 'ok'})


class WithdrawView(APIView):
    """
    Request a withdrawal.
    POST /api/payments/withdraw/
    Body: { "amount": 500, "withdrawal_method": "upi" }
    """
    permission_classes = [IsAuthenticated]

    @db_transaction.atomic
    def post(self, request):
        serializer = WithdrawalRequestSerializer(
            data=request.data,
            context={'request': request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        amount_inr = data['amount']
        amount_paise = int(amount_inr * 100)
        user = request.user

        # Calculate TDS if applicable
        tds_amount = 0
        if amount_paise > settings.TOP11_TDS_THRESHOLD * 100:
            tds_amount = int(amount_paise * settings.TOP11_TDS_RATE)

        net_amount = amount_paise - tds_amount

        # Deduct from winnings balance
        wallet = user.wallet
        wallet.winnings_balance -= amount_paise
        wallet.save()

        # Record TDS deduction
        if tds_amount > 0:
            Transaction.objects.create(
                user=user,
                transaction_type='tds',
                status='success',
                amount=tds_amount,
                wallet_bucket='winnings',
                description=f'TDS @30% on withdrawal of ₹{amount_inr}',
                idempotency_key=f'tds_{uuid.uuid4().hex}',
            )

        # Create withdrawal record
        transfer_id = f"WD_{user.id}_{uuid.uuid4().hex[:8].upper()}"
        withdrawal = Withdrawal.objects.create(
            user=user,
            amount=net_amount,
            bank_account=user.bank_account_number if data['withdrawal_method'] == 'bank' else '',
            bank_ifsc=user.bank_ifsc if data['withdrawal_method'] == 'bank' else '',
            upi_id=user.upi_id if data['withdrawal_method'] == 'upi' else '',
            cashfree_transfer_id=transfer_id,
            status='processing',
        )

        # Initiate payout via Cashfree
        success, response_data, error = initiate_payout(
            user=user,
            amount_inr=net_amount / 100,
            transfer_id=transfer_id,
        )

        if not success:
            # Payout failed — refund to wallet
            wallet.winnings_balance += amount_paise
            wallet.save()
            withdrawal.status = 'failed'
            withdrawal.rejection_reason = error
            withdrawal.save()
            return Response(
                {'error': f'Payout failed: {error}'},
                status=status.HTTP_502_BAD_GATEWAY
            )

        # Record withdrawal transaction
        Transaction.objects.create(
            user=user,
            transaction_type='withdrawal',
            status='success',
            amount=net_amount,
            wallet_bucket='winnings',
            description=f'Withdrawal ₹{net_amount/100:.2f} via {data["withdrawal_method"].upper()}',
            idempotency_key=transfer_id,
        )

        return Response({
            'message': 'Withdrawal initiated successfully.',
            'withdrawal_id': str(withdrawal.id),
            'amount_requested': float(amount_inr),
            'tds_deducted': round(tds_amount / 100, 2),
            'amount_to_receive': round(net_amount / 100, 2),
            'method': data['withdrawal_method'],
            'status': 'processing',
        }, status=status.HTTP_201_CREATED)


class TransactionHistoryView(APIView):
    """
    Full transaction history for logged-in user.
    GET /api/payments/transactions/
    GET /api/payments/transactions/?type=deposit
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        transactions = Transaction.objects.filter(
            user=request.user
        ).order_by('-created_at')

        txn_type = request.query_params.get('type')
        if txn_type:
            transactions = transactions.filter(transaction_type=txn_type)

        transactions = transactions[:50]
        serializer = TransactionSerializer(transactions, many=True)
        return Response({
            'count': len(transactions),
            'transactions': serializer.data,
        })


class WithdrawalHistoryView(APIView):
    """
    Withdrawal request history.
    GET /api/payments/withdrawals/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        withdrawals = Withdrawal.objects.filter(
            user=request.user
        ).order_by('-created_at')

        serializer = WithdrawalSerializer(withdrawals, many=True)
        return Response({
            'count': withdrawals.count(),
            'withdrawals': serializer.data,
        })


class KYCView(APIView):
    """
    Submit KYC details (PAN + bank/UPI).
    POST /api/payments/kyc/
    Required before withdrawals.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Check KYC status"""
        user = request.user
        return Response({
            'is_kyc_done': user.is_kyc_done,
            'pan_verified': user.pan_verified,
            'has_bank': bool(user.bank_account_number),
            'has_upi': bool(user.upi_id),
        })

    def post(self, request):
        serializer = KYCSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        user = request.user

        user.pan_number = data['pan_number']
        user.pan_verified = True   # In production: verify via PAN API
        if data.get('bank_account_number'):
            user.bank_account_number = data['bank_account_number']
            user.bank_ifsc = data['bank_ifsc']
            user.bank_name = data.get('bank_name', '')
        if data.get('upi_id'):
            user.upi_id = data['upi_id']
        user.is_kyc_done = True
        user.save()

        return Response({
            'message': 'KYC details saved successfully. You can now withdraw funds.',
            'is_kyc_done': True,
        })