from decimal import Decimal

from django.contrib.auth.models import User
from django.db.models import Q, Sum
from rest_framework import serializers

from .models import (
    SavingsGoal,
    SavingsTransaction,
    TransactionProof,
)


class UserSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = User

        fields = (
            "id",
            "username",
        )


class GoalMemberSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    profile_picture = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "display_name",
            "profile_picture",
        )

    def get_display_name(self, obj):
        profile = getattr(obj, "profile", None)

        if profile and profile.display_name:
            return profile.display_name

        return obj.username

    def get_profile_picture(self, obj):
        profile = getattr(obj, "profile", None)

        if not profile:
            return None

        if not profile.profile_picture:
            return None

        request = self.context.get("request")

        if request:
            return request.build_absolute_uri(
                profile.profile_picture.url
            )

        return profile.profile_picture.url


class TransactionProofSerializer(
    serializers.ModelSerializer
):
    class Meta:
        model = TransactionProof

        fields = (
            "id",
            "file",
            "uploaded_at",
        )

        read_only_fields = (
            "id",
            "uploaded_at",
        )

    def validate_file(self, file):
        max_size = 10 * 1024 * 1024

        if file.size > max_size:
            raise serializers.ValidationError(
                "Proof file must not exceed 10 MB."
            )

        allowed_types = {
            "image/jpeg",
            "image/png",
            "image/webp",
            "application/pdf",
        }

        if file.content_type not in allowed_types:
            raise serializers.ValidationError(
                "Only JPG, PNG, WEBP, and PDF files are allowed."
            )

        return file


class SavingsTransactionSerializer(
    serializers.ModelSerializer
):
    user = UserSimpleSerializer(
        read_only=True
    )

    recipient = UserSimpleSerializer(
        read_only=True
    )

    recipient_id = serializers.IntegerField(
        write_only=True,
        required=False,
        allow_null=True,
    )

    proof = TransactionProofSerializer(
        read_only=True
    )

    class Meta:
        model = SavingsTransaction

        fields = (
            "id",
            "goal",
            "user",
            "recipient",
            "recipient_id",
            "transaction_type",
            "amount",
            "transaction_date",
            "bank_reference",
            "notes",
            "proof",
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "goal",
            "user",
            "recipient",
            "proof",
            "created_at",
            "updated_at",
        )

    def validate_amount(self, value):
        if value <= Decimal("0.00"):
            raise serializers.ValidationError(
                "Amount must be greater than zero."
            )

        return value

    def validate(self, attrs):
        transaction_type = attrs.get(
            "transaction_type",
            self.instance.transaction_type
            if self.instance
            else SavingsTransaction.DEPOSIT,
        )

        recipient_id = attrs.get(
            "recipient_id"
        )

        if transaction_type == SavingsTransaction.TRANSFER:
            if not recipient_id:
                raise serializers.ValidationError({
                    "recipient_id": (
                        "Please select who will receive "
                        "the transfer."
                    )
                })

            request = self.context.get(
                "request"
            )

            if (
                not request
                or not request.user.is_authenticated
            ):
                raise serializers.ValidationError(
                    "Authentication is required."
                )

            goal = (
                SavingsGoal.objects
                .filter(
                    members=request.user,
                    is_active=True,
                )
                .first()
            )

            if not goal:
                raise serializers.ValidationError({
                    "detail": (
                        "You are not a member of an "
                        "active shared savings goal."
                    )
                })

            member_ids = set(
                goal.members.values_list(
                    "id",
                    flat=True,
                )
            )

            if recipient_id not in member_ids:
                raise serializers.ValidationError({
                    "recipient_id": (
                        "The recipient must be a member "
                        "of your shared savings goal."
                    )
                })

            if recipient_id == request.user.id:
                raise serializers.ValidationError({
                    "recipient_id": (
                        "You cannot transfer money to yourself."
                    )
                })

        elif recipient_id:
            raise serializers.ValidationError({
                "recipient_id": (
                    "Deposits cannot have a transfer recipient."
                )
            })

        return attrs


class SavingsGoalSerializer(
    serializers.ModelSerializer
):
    """
    Serializes a shared savings goal.

    IMPORTANT:
    `members` contains ALL members of the shared goal,
    regardless of whether they have contributed money.

    Example:

        Kyle       -> ₱30,000
        Partner    -> ₱0

    Both Kyle and Partner are returned in `members`.
    """

    member_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
    )

    members = GoalMemberSerializer(
        many=True,
        read_only=True,
    )

    total_saved = serializers.SerializerMethodField()

    total_contributions = (
        serializers.SerializerMethodField()
    )

    total_borrowed = (
        serializers.SerializerMethodField()
    )

    outstanding_borrowings = (
        serializers.SerializerMethodField()
    )

    available_savings = (
        serializers.SerializerMethodField()
    )

    remaining_amount = (
        serializers.SerializerMethodField()
    )

    progress_percentage = (
        serializers.SerializerMethodField()
    )

    def create(self, validated_data):
        # member_ids is only used for selecting goal members.
        # It is not a field on the SavingsGoal model.
        validated_data.pop("member_ids", None)

        return SavingsGoal.objects.create(
            **validated_data
        )

    class Meta:
        model = SavingsGoal

        fields = (
            "id",
            "name",
            "target_amount",
            "members",
            "member_ids",
            "start_date",
            "is_active",

            "total_saved",
            "total_contributions",
            "total_borrowed",
            "outstanding_borrowings",
            "available_savings",

            "remaining_amount",
            "progress_percentage",

            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "members",
            "start_date",

            "total_saved",
            "total_contributions",
            "total_borrowed",
            "outstanding_borrowings",
            "available_savings",

            "remaining_amount",
            "progress_percentage",

            "created_at",
            "updated_at",
        )

    def _get_contributions(self, obj):
        return (
            obj.transactions.aggregate(
                total=Sum("amount")
            )["total"]
            or Decimal("0.00")
        )

    def _get_borrowings(self, obj):
        from borrowings.models import Borrowing

        member_ids = list(
            obj.members.values_list(
                "id",
                flat=True,
            )
        )

        return Borrowing.objects.filter(
            Q(
                borrower_id__in=member_ids
            )
            |
            Q(
                lender_id__in=member_ids
            )
        ).distinct()

    def _get_total_borrowed(self, obj):
        borrowings = self._get_borrowings(
            obj
        )

        return (
            borrowings.aggregate(
                total=Sum("amount")
            )["total"]
            or Decimal("0.00")
        )

    def _get_total_repaid(self, obj):
        from borrowings.models import Repayment

        borrowings = self._get_borrowings(
            obj
        )

        return (
            Repayment.objects.filter(
                borrowing__in=borrowings,
            ).aggregate(
                total=Sum("amount")
            )["total"]
            or Decimal("0.00")
        )

    def get_total_contributions(self, obj):
        return self._get_contributions(
            obj
        )

    def get_total_saved(self, obj):
        return self.get_available_savings(
            obj
        )

    def get_total_borrowed(self, obj):
        return self._get_total_borrowed(
            obj
        )

    def get_outstanding_borrowings(self, obj):
        total_borrowed = (
            self._get_total_borrowed(obj)
        )

        total_repaid = (
            self._get_total_repaid(obj)
        )

        return max(
            total_borrowed - total_repaid,
            Decimal("0.00"),
        )

    def get_available_savings(self, obj):
        contributions = (
            self._get_contributions(obj)
        )

        outstanding = (
            self.get_outstanding_borrowings(
                obj
            )
        )

        return max(
            contributions - outstanding,
            Decimal("0.00"),
        )

    def get_remaining_amount(self, obj):
        available = (
            self.get_available_savings(obj)
        )

        return max(
            obj.target_amount - available,
            Decimal("0.00"),
        )

    def get_progress_percentage(self, obj):
        available = (
            self.get_available_savings(obj)
        )

        if (
            obj.target_amount
            <= Decimal("0.00")
        ):
            return Decimal("0.00")

        percentage = (
            available
            / obj.target_amount
        ) * Decimal("100")

        return min(
            percentage,
            Decimal("100.00"),
        )


class SavingsDashboardSerializer(
    serializers.Serializer
):
    goal = SavingsGoalSerializer()

    total_saved = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    total_contributions = (
        serializers.DecimalField(
            max_digits=12,
            decimal_places=2,
        )
    )

    total_borrowed = (
        serializers.DecimalField(
            max_digits=12,
            decimal_places=2,
        )
    )

    outstanding_borrowings = (
        serializers.DecimalField(
            max_digits=12,
            decimal_places=2,
        )
    )

    available_savings = (
        serializers.DecimalField(
            max_digits=12,
            decimal_places=2,
        )
    )

    remaining_amount = (
        serializers.DecimalField(
            max_digits=12,
            decimal_places=2,
        )
    )

    progress_percentage = (
        serializers.DecimalField(
            max_digits=6,
            decimal_places=2,
        )
    )

    total_transactions = (
        serializers.IntegerField()
    )

    average_monthly_savings = (
        serializers.DecimalField(
            max_digits=12,
            decimal_places=2,
        )
    )

    estimated_months_remaining = (
        serializers.DecimalField(
            max_digits=12,
            decimal_places=2,
            allow_null=True,
        )
    )

    contributions = serializers.ListField()