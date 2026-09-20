from .models import Notification


def create_notification(
    user,
    notification_type,
    title,
    message,
):
    return Notification.objects.create(
        user=user,
        notification_type=notification_type,
        title=title,
        message=message,
    )