import hmac
import hashlib
import requests
import uuid
from django.conf import settings


def get_cashfree_headers():
    """Headers required for all Cashfree API calls"""
    return {
        'x-api-version': '2023-08-01',
        'x-client-id': settings.CASHFREE_APP_ID,
        'x-client-secret': settings.CASHFREE_SECRET_KEY,
        'Content-Type': 'application/json',
    }


def get_cashfree_base_url():
    """Use sandbox URL in TEST mode, production in PROD"""
    if settings.CASHFREE_ENVIRONMENT == 'TEST':
        return 'https://sandbox.cashfree.com/pg'
    return 'https://api.cashfree.com/pg'


def create_payment_order(user, amount_inr, return_url=None):
    """
    Create a Cashfree payment order.
    amount_inr: amount in rupees (e.g. 100 for ₹100)
    Returns: (order_id, payment_session_id, error)
    """
    order_id = f"TOP11_{user.id}_{uuid.uuid4().hex[:8].upper()}"

    payload = {
        "order_id": order_id,
        "order_amount": float(amount_inr),
        "order_currency": "INR",
        "customer_details": {
            "customer_id": str(user.id),
            "customer_email": user.email,
            "customer_phone": user.mobile or "9999999999",
            "customer_name": user.full_name or user.email.split('@')[0],
        },
        "order_meta": {
            "return_url": return_url or "https://yourdomain.com/payment/success",
            "notify_url": f"{settings.SITE_URL}/api/payments/webhook/cashfree/",
        },
    }

    try:
        response = requests.post(
            f"{get_cashfree_base_url()}/orders",
            json=payload,
            headers=get_cashfree_headers(),
            timeout=10,
        )
        data = response.json()

        if response.status_code == 200:
            return order_id, data.get('payment_session_id'), None
        else:
            error_msg = data.get('message', 'Cashfree order creation failed')
            return None, None, error_msg

    except requests.exceptions.RequestException as e:
        return None, None, f"Network error: {str(e)}"


def verify_webhook_signature(raw_body, timestamp, signature):
    """
    Verify Cashfree webhook signature.
    Cashfree signs: timestamp + raw_body
    We verify using HMAC-SHA256 with our secret key.
    Returns True if valid, False if tampered.
    """
    message = f"{timestamp}{raw_body}"
    expected = hmac.new(
        settings.CASHFREE_SECRET_KEY.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    # Use hmac.compare_digest to prevent timing attacks
    return hmac.compare_digest(expected, signature)


def verify_payment_order(order_id):
    """
    Verify payment status directly with Cashfree.
    Use this as a backup if webhook is not received.
    Returns: (status, amount_paid, error)
    status can be: 'PAID', 'ACTIVE', 'EXPIRED', 'TERMINATED'
    """
    try:
        response = requests.get(
            f"{get_cashfree_base_url()}/orders/{order_id}",
            headers=get_cashfree_headers(),
            timeout=10,
        )
        data = response.json()

        if response.status_code == 200:
            return data.get('order_status'), data.get('order_amount'), None
        else:
            return None, None, data.get('message', 'Verification failed')

    except requests.exceptions.RequestException as e:
        return None, None, f"Network error: {str(e)}"


def initiate_payout(user, amount_inr, transfer_id):
    """
    Send money to user's bank/UPI via Cashfree Payouts.
    amount_inr: amount in rupees
    Returns: (success, response_data, error)
    """
    if settings.CASHFREE_ENVIRONMENT == 'TEST':
        base_url = 'https://payout-gamma.cashfree.com'
    else:
        base_url = 'https://payout-api.cashfree.com'

    # Determine transfer mode
    if user.upi_id:
        transfer_mode = 'upi'
        account_details = {'vpa': user.upi_id}
    elif user.bank_account_number and user.bank_ifsc:
        transfer_mode = 'banktransfer'
        account_details = {
            'bank_account': user.bank_account_number,
            'ifsc': user.bank_ifsc,
        }
    else:
        return False, None, "No bank account or UPI ID found."

    payload = {
        "transfer_id": transfer_id,
        "transfer_amount": float(amount_inr),
        "transfer_currency": "INR",
        "transfer_mode": transfer_mode,
        "beneficiary_details": {
            "beneficiary_id": str(user.id),
            "beneficiary_name": user.full_name or "TOP11 User",
            "beneficiary_email": user.email,
            "beneficiary_phone": user.mobile or "9999999999",
            **account_details,
        },
    }

    try:
        response = requests.post(
            f"{base_url}/payout/v1/requestAsyncTransfer",
            json=payload,
            headers=get_cashfree_headers(),
            timeout=10,
        )
        data = response.json()

        if response.status_code == 200 and data.get('status') == 'SUCCESS':
            return True, data, None
        else:
            return False, data, data.get('message', 'Payout failed')

    except requests.exceptions.RequestException as e:
        return False, None, f"Network error: {str(e)}"