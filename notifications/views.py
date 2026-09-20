from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification
from .serializers import NotificationSerializer


class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notifications = (
            Notification.objects
            .filter(user=request.user)
            .order_by("-created_at")
        )

        serializer = NotificationSerializer(
            notifications,
            many=True,
        )

        unread_count = notifications.filter(
            is_read=False
        ).count()

        return Response({
            "notifications": serializer.data,
            "unread_count": unread_count,
        })


class NotificationMarkReadView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        try:
            notification = Notification.objects.get(
                pk=pk,
                user=request.user,
            )
        except Notification.DoesNotExist:
            return Response(
                {
                    "detail": "Notification not found."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        notification.is_read = True
        notification.save(
            update_fields=["is_read"]
        )

        return Response({
            "detail": "Notification marked as read."
        })


class NotificationMarkAllReadView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        updated = (
            Notification.objects
            .filter(
                user=request.user,
                is_read=False,
            )
            .update(is_read=True)
        )

        return Response({
            "detail": "All notifications marked as read.",
            "updated": updated,
        })


class NotificationDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        try:
            notification = Notification.objects.get(
                pk=pk,
                user=request.user,
            )
        except Notification.DoesNotExist:
            return Response(
                {
                    "detail": "Notification not found."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        notification.delete()

        return Response(
            status=status.HTTP_204_NO_CONTENT
        )