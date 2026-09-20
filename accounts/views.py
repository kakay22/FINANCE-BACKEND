from django.contrib.auth.models import User
from django.http.multipartparser import MultiPartParser

from accounts.models import UserProfile
from accounts.models import UserProfile
from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import RegisterSerializer

from django.contrib.auth.password_validation import validate_password
from rest_framework.views import APIView
from rest_framework import status

from rest_framework.parsers import JSONParser, MultiPartParser, FormParser

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    parser_classes = [
        MultiPartParser,
        FormParser,
        JSONParser,
    ]

    def get_profile_data(self, request, profile):
        profile_picture = None

        if profile.profile_picture:
            profile_picture = request.build_absolute_uri(
                profile.profile_picture.url
            )

        return {
            "id": request.user.id,
            "username": request.user.username,
            "email": request.user.email,
            "display_name": profile.display_name,
            "profile_picture": profile_picture,
        }

    def get(self, request):
        profile, _ = UserProfile.objects.get_or_create(
            user=request.user
        )

        return Response(
            self.get_profile_data(request, profile)
        )

    def patch(self, request):
        profile, _ = UserProfile.objects.get_or_create(
            user=request.user
        )

        print("========== PROFILE UPDATE ==========")
        print("REQUEST DATA:", request.data)
        print("REQUEST FILES:", request.FILES)

        # -------------------------
        # Username
        # -------------------------

        username = request.data.get("username")

        if username is not None:
            username = username.strip()

            if not username:
                return Response(
                    {
                        "username": [
                            "Username is required."
                        ]
                    },
                    status=400,
                )

            username_exists = (
                User.objects
                .exclude(pk=request.user.pk)
                .filter(username__iexact=username)
                .exists()
            )

            if username_exists:
                return Response(
                    {
                        "username": [
                            "This username is already taken."
                        ]
                    },
                    status=400,
                )

            request.user.username = username

        # -------------------------
        # Email
        # -------------------------

        email = request.data.get("email")

        if email is not None:
            request.user.email = email.strip()

        # -------------------------
        # Profile picture
        # -------------------------

        uploaded_picture = request.FILES.get(
            "profile_picture"
        )

        print(
            "UPLOADED PICTURE:",
            uploaded_picture
        )

        if uploaded_picture:

            print(
                "PICTURE NAME:",
                uploaded_picture.name
            )

            print(
                "PICTURE SIZE:",
                uploaded_picture.size
            )

            print(
                "PICTURE TYPE:",
                uploaded_picture.content_type
            )

            # Delete old picture
            if profile.profile_picture:
                profile.profile_picture.delete(
                    save=False
                )

            # Assign new picture
            profile.profile_picture = uploaded_picture

        # -------------------------
        # Save
        # -------------------------

        request.user.save()
        profile.save()

        print(
            "PROFILE PICTURE AFTER SAVE:",
            profile.profile_picture.name
            if profile.profile_picture
            else None
        )

        print(
            "PROFILE PICTURE URL:",
            profile.profile_picture.url
            if profile.profile_picture
            else None
        )

        print("====================================")

        return Response(
            self.get_profile_data(
                request,
                profile
            )
        )


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        current_password = request.data.get("current_password")
        new_password = request.data.get("new_password")
        confirm_password = request.data.get("confirm_password")

        if not current_password:
            return Response(
                {"current_password": "Current password is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not new_password:
            return Response(
                {"new_password": "New password is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not confirm_password:
            return Response(
                {"confirm_password": "Please confirm your new password."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify current password
        if not request.user.check_password(current_password):
            return Response(
                {"current_password": "Current password is incorrect."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Make sure the new passwords match
        if new_password != confirm_password:
            return Response(
                {"confirm_password": "New passwords do not match."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Don't allow the same password
        if request.user.check_password(new_password):
            return Response(
                {
                    "new_password":
                        "Your new password must be different from your current password."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Django's configured password validators
        try:
            validate_password(new_password, request.user)
        except Exception as error:
            return Response(
                {"new_password": list(error.messages)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request.user.set_password(new_password)
        request.user.save()

        return Response({
            "detail": "Password changed successfully."
        })