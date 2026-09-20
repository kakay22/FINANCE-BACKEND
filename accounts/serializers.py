from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import UserProfile


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        validators=[validate_password],
    )

    password_confirm = serializers.CharField(
        write_only=True,
    )

    display_name = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    class Meta:
        model = User
        fields = (
            "username",
            "email",
            "password",
            "password_confirm",
            "display_name",
        )

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({
                "password_confirm": "Passwords do not match."
            })

        return attrs

    def create(self, validated_data):
        display_name = validated_data.pop(
            "display_name",
            "",
        )

        validated_data.pop("password_confirm")

        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
        )

        UserProfile.objects.create(
            user=user,
            display_name=display_name,
        )

        return user