from django.contrib.auth.models import User
from django.db import models


class Notification(models.Model):

    TRANSACTION = "TRANSACTION"
    BORROWING = "BORROWING"
    REPAYMENT = "REPAYMENT"
    REMINDER = "REMINDER"
    SYSTEM = "SYSTEM"

    TYPE_CHOICES = [
        (TRANSACTION, "Transaction"),
        (BORROWING, "Borrowing"),
        (REPAYMENT, "Repayment"),
        (REMINDER, "Reminder"),
        (SYSTEM, "System"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notifications",
    )

    notification_type = models.CharField(
        max_length=30,
        choices=TYPE_CHOICES,
    )

    title = models.CharField(
        max_length=200,
    )

    message = models.TextField()

    is_read = models.BooleanField(
        default=False,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    def __str__(self):
        return f"{self.user.username} - {self.title}"