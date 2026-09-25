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


class UserProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(
        source="user.username",
        read_only=True,
    )

    email = serializers.EmailField(
        source="user.email",
        read_only=True,
    )

    profile_picture = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = (
            "id",
            "username",
            "email",
            "display_name",
            "profile_picture",
        )
        read_only_fields = (
            "id",
            "username",
            "email",
            "profile_picture",
        )

    def get_profile_picture(self, obj):
        if not obj.profile_picture:
            return None

        request = self.context.get("request")

        if request:
            return request.build_absolute_uri(
                obj.profile_picture.url
            )

        return obj.profile_picture.url

class GoalMemberSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    profile_picture = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "display_name",
            "profile_picture",
        )

    def get_display_name(self, obj):
        try:
            profile = obj.profile
            return profile.display_name or obj.username
        except UserProfile.DoesNotExist:
            return obj.username

    def get_profile_picture(self, obj):
        try:
            profile = obj.profile

            if not profile.profile_picture:
                return None

            request = self.context.get("request")

            if request:
                return request.build_absolute_uri(
                    profile.profile_picture.url
                )

            return profile.profile_picture.url

        except UserProfile.DoesNotExist:
            return None