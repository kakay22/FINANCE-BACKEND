from decimal import Decimal

from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.contrib.auth.models import User

from rest_framework import generics, status
from rest_framework.parsers import (
    FormParser,
    JSONParser,
    MultiPartParser,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from notifications.models import Notification
from notifications.utils import create_notification

from .models import (
    SavingsGoal,
    SavingsTransaction,
    TransactionProof,
)

from .serializers import (
    SavingsGoalSerializer,
    SavingsTransactionSerializer,
    TransactionProofSerializer,
)


class UserGoalMixin:
    def get_goal(self):
        return get_object_or_404(
            SavingsGoal,
            members=self.request.user,
            is_active=True,
        )


class SavingsGoalView(
    UserGoalMixin,
    APIView,
):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        goal = self.get_goal()

        serializer = SavingsGoalSerializer(
            goal,
            context={"request": request},
        )

        return Response(serializer.data)

    def post(self, request):
        # Selected additional members.
        # The creator is added automatically below.
        member_ids = request.data.get(
            "member_ids",
            [],
        )

        # Protect against malformed frontend data.
        if not isinstance(member_ids, list):
            member_ids = []

        # Find the creator's current active goal.
        existing_goal = (
            SavingsGoal.objects
            .filter(
                members=request.user,
                is_active=True,
            )
            .first()
        )

        if existing_goal:
            # Allow a new goal only when the current goal
            # has already reached its target.
            if (
                existing_goal.total_saved
                >= existing_goal.target_amount
            ):
                existing_goal.is_active = False

                existing_goal.save(
                    update_fields=[
                        "is_active",
                        "updated_at",
                    ]
                )

            else:
                return Response(
                    {
                        "detail": (
                            "You already have an active "
                            "savings goal."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Validate and create the new goal.
        serializer = SavingsGoalSerializer(
            data=request.data,
            context={
                "request": request,
            },
        )

        serializer.is_valid(
            raise_exception=True
        )

        goal = serializer.save()

        # Creator is always a member.
        goal.members.add(request.user)

        # Add selected additional members.
        selected_members = (
            User.objects
            .filter(
                id__in=member_ids,
                is_active=True,
            )
            .exclude(
                id=request.user.id
            )
        )

        goal.members.add(
            *selected_members
        )

        # Return the completed goal object,
        # including its members.
        response_serializer = SavingsGoalSerializer(
            goal,
            context={
                "request": request,
            },
        )

        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED,
        )


class SavingsTransactionListCreateView(
    UserGoalMixin,
    generics.ListCreateAPIView,
):
    permission_classes = [IsAuthenticated]

    serializer_class = SavingsTransactionSerializer

    def get_queryset(self):
        goal = self.get_goal()

        return (
            SavingsTransaction.objects
            .filter(goal=goal)
            .select_related("user", "goal")
            .prefetch_related("proof")
            .order_by(
                "-transaction_date",
                "-created_at",
            )
        )

    def perform_create(self, serializer):
        goal = self.get_goal()
        user = self.request.user

        transaction = serializer.save(
            user=user,
            goal=goal,
        )

        # IMPORTANT:
        # Reaching the savings target does NOT deactivate the goal.
        # The completed goal remains active until a new goal is created.

        if (
            transaction.transaction_type
            == SavingsTransaction.DEPOSIT
        ):
            # Notify the user who made the deposit.
            create_notification(
                user=user,
                notification_type=Notification.TRANSACTION,
                title="Money deposited",
                message=(
                    f"₱{transaction.amount:,.2f} "
                    f"was added to {goal.name}."
                ),
            )

            # Notify the other members of the shared goal.
            other_members = goal.members.exclude(
                id=user.id
            )

            for member in other_members:
                create_notification(
                    user=member,
                    notification_type=Notification.TRANSACTION,
                    title="New deposit",
                    message=(
                        f"{user.username} deposited "
                        f"₱{transaction.amount:,.2f} "
                        f"into {goal.name}."
                    ),
                )

        elif (
            transaction.transaction_type
            == SavingsTransaction.TRANSFER
        ):
            recipient = transaction.recipient

            # Notify sender.
            create_notification(
                user=user,
                notification_type=Notification.TRANSACTION,
                title="Transfer completed",
                message=(
                    f"₱{transaction.amount:,.2f} "
                    f"was transferred to "
                    f"{recipient.username}."
                ),
            )

            # Notify recipient.
            create_notification(
                user=recipient,
                notification_type=Notification.TRANSACTION,
                title="Money received",
                message=(
                    f"You received "
                    f"₱{transaction.amount:,.2f} "
                    f"from {user.username}."
                ),
            )

class SavingsTransactionDetailView(
    UserGoalMixin,
    generics.RetrieveUpdateDestroyAPIView,
):
    permission_classes = [IsAuthenticated]

    serializer_class = SavingsTransactionSerializer

    def get_queryset(self):
        goal = self.get_goal()

        return (
            SavingsTransaction.objects
            .filter(goal=goal)
            .select_related("user", "goal")
            .prefetch_related("proof")
        )

    def perform_update(self, serializer):
        transaction = self.get_object()

        if transaction.user != self.request.user:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied(
                "You can only edit your own transactions."
            )

        serializer.save()

    def perform_destroy(self, instance):
        if instance.user != self.request.user:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied(
                "You can only delete your own transactions."
            )

        instance.delete()


class TransactionProofView(APIView):
    permission_classes = [IsAuthenticated]

    parser_classes = (
        MultiPartParser,
        FormParser,
        JSONParser,
    )

    def post(self, request, transaction_id):
        transaction = get_object_or_404(
            SavingsTransaction,
            id=transaction_id,
            goal__members=request.user,
        )

        if transaction.user != request.user:
            return Response(
                {
                    "detail": (
                        "Only the person who created "
                        "the transaction can upload proof."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if hasattr(transaction, "proof"):
            return Response(
                {
                    "detail": (
                        "This transaction already has proof."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        file = request.FILES.get("file")

        if not file:
            return Response(
                {
                    "detail": "A proof file is required."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = TransactionProofSerializer(
            data={"file": file},
        )

        serializer.is_valid(
            raise_exception=True
        )

        proof = serializer.save(
            transaction=transaction,
        )

        return Response(
            TransactionProofSerializer(proof).data,
            status=status.HTTP_201_CREATED,
        )


class SavingsDashboardView(
    UserGoalMixin,
    APIView,
):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        goal = self.get_goal()

        transactions = (
            SavingsTransaction.objects
            .filter(goal=goal)
            .select_related("user")
            .prefetch_related("proof")
            .order_by(
                "-transaction_date",
                "-created_at",
            )
        )

        # --------------------------------------------------
        # TOTAL CONTRIBUTIONS
        # --------------------------------------------------

        total_contributions = (
            transactions.aggregate(
                total=Sum("amount")
            )["total"]
            or Decimal("0.00")
        )

        # --------------------------------------------------
        # SHARED MEMBERS
        # --------------------------------------------------

        members = (
            goal.members
            .all()
            .select_related("profile")
        )

        member_ids = list(
            members.values_list(
                "id",
                flat=True,
            )
        )

        # --------------------------------------------------
        # BORROWINGS
        #
        # A borrowing is money taken out of the shared
        # housing savings.
        # --------------------------------------------------

        from borrowings.models import (
            Borrowing,
            Repayment,
        )

        borrowings = Borrowing.objects.filter(
            Q(borrower_id__in=member_ids)
            | Q(lender_id__in=member_ids)
        ).distinct()

        # --------------------------------------------------
        # TOTAL BORROWED
        # --------------------------------------------------

        total_borrowed = (
            borrowings.aggregate(
                total=Sum("amount")
            )["total"]
            or Decimal("0.00")
        )

        # --------------------------------------------------
        # TOTAL REPAYMENTS
        # --------------------------------------------------

        total_repaid = (
            Repayment.objects.filter(
                borrowing__in=borrowings,
            ).aggregate(
                total=Sum("amount")
            )["total"]
            or Decimal("0.00")
        )

        # --------------------------------------------------
        # OUTSTANDING BORROWINGS
        # --------------------------------------------------

        outstanding_borrowings = max(
            total_borrowed - total_repaid,
            Decimal("0.00"),
        )

        # --------------------------------------------------
        # AVAILABLE SAVINGS
        # --------------------------------------------------

        available_savings = max(
            total_contributions
            - outstanding_borrowings,
            Decimal("0.00"),
        )

        # --------------------------------------------------
        # REMAINING GOAL
        # --------------------------------------------------

        remaining_amount = max(
            goal.target_amount - available_savings,
            Decimal("0.00"),
        )

        # --------------------------------------------------
        # PROGRESS
        # --------------------------------------------------

        if goal.target_amount > 0:
            progress_percentage = (
                available_savings
                / goal.target_amount
            ) * Decimal("100")

            progress_percentage = min(
                progress_percentage,
                Decimal("100.00"),
            )
        else:
            progress_percentage = Decimal("0.00")

        # --------------------------------------------------
        # TRANSACTION COUNT
        # --------------------------------------------------

        total_transactions = transactions.count()

        # --------------------------------------------------
        # CONTRIBUTIONS BY SHARED MEMBER
        #
        # IMPORTANT:
        # We use goal.members instead of only transactions.
        #
        # This means both partners appear even when one
        # has contributed ₱0.00 so far.
        # --------------------------------------------------

        contribution_totals = (
            transactions
            .values("user_id")
            .annotate(total=Sum("amount"))
        )

        contribution_map = {
            item["user_id"]: (
                item["total"]
                or Decimal("0.00")
            )
            for item in contribution_totals
        }

        contributions = []

        for member in members:
            profile = getattr(
                member,
                "profile",
                None,
            )

            profile_picture = None

            if (
                profile
                and profile.profile_picture
            ):
                profile_picture = request.build_absolute_uri(
                    profile.profile_picture.url
                )

            contributions.append(
                {
                    "user_id": member.id,
                    "username": member.username,
                    "display_name": (
                        profile.display_name
                        if profile
                        else ""
                    ),
                    "profile_picture": (
                        profile_picture
                    ),
                    "amount": contribution_map.get(
                        member.id,
                        Decimal("0.00"),
                    ),
                }
            )

        # --------------------------------------------------
        # SORT CONTRIBUTORS
        #
        # Users who contributed the most appear first.
        # --------------------------------------------------

        contributions.sort(
            key=lambda item: item["amount"],
            reverse=True,
        )

        # --------------------------------------------------
        # MONTHLY AVERAGE
        # --------------------------------------------------

        today = timezone.now().date()

        months_elapsed = (
            (
                today.year
                - goal.start_date.year
            ) * 12
            + today.month
            - goal.start_date.month
        )

        months_elapsed = max(
            months_elapsed,
            1,
        )

        average_monthly_savings = (
            total_contributions
            / Decimal(months_elapsed)
        )

        # --------------------------------------------------
        # ESTIMATED TIME TO GOAL
        # --------------------------------------------------

        if (
            remaining_amount > 0
            and average_monthly_savings > 0
        ):
            estimated_months_remaining = (
                remaining_amount
                / average_monthly_savings
            )
        else:
            estimated_months_remaining = None

        # --------------------------------------------------
        # RECENT TRANSACTIONS
        # --------------------------------------------------

        recent_transactions = [
            {
                "id": transaction.id,
                "user": {
                    "id": transaction.user.id,
                    "username": (
                        transaction.user.username
                    ),
                },
                "transaction_type": (
                    transaction.transaction_type
                ),
                "amount": transaction.amount,
                "transaction_date": (
                    transaction.transaction_date
                ),
                "bank_reference": (
                    transaction.bank_reference
                ),
                "notes": transaction.notes,
                "has_proof": hasattr(
                    transaction,
                    "proof",
                ),
            }
            for transaction in transactions[:5]
        ]

        # --------------------------------------------------
        # RESPONSE
        # --------------------------------------------------

        return Response(
            {
                "goal": SavingsGoalSerializer(
                    goal,
                    context={
                        "request": request,
                    },
                ).data,

                "total_saved": (
                    total_contributions
                ),

                "total_contributions": (
                    total_contributions
                ),

                "total_borrowed": (
                    total_borrowed
                ),

                "outstanding_borrowings": (
                    outstanding_borrowings
                ),

                "available_savings": (
                    available_savings
                ),

                "remaining_amount": (
                    remaining_amount
                ),

                "progress_percentage": (
                    progress_percentage
                ),

                "total_transactions": (
                    total_transactions
                ),

                "average_monthly_savings": (
                    average_monthly_savings
                ),

                "estimated_months_remaining": (
                    estimated_months_remaining
                ),

                "contributions": contributions,

                "recent_transactions": (
                    recent_transactions
                ),
            }
        )