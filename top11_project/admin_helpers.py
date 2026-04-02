from scoring.models import AuditLog


def log_admin_action(admin_user, action, model_name='', object_id='',
                     old_value=None, new_value=None, ip_address=None):
    """
    Record every admin action in the audit log.
    Call this from every admin action/view that changes data.
    """
    AuditLog.objects.create(
        admin_user=admin_user,
        action=action,
        model_name=model_name,
        object_id=str(object_id),
        old_value=old_value,
        new_value=new_value,
        ip_address=ip_address,
    )


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')