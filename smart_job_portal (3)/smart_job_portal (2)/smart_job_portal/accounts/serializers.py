from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from .models import UserProfile, Resume


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model  = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']


class UserProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model  = UserProfile
        fields = ['id', 'user', 'role', 'phone', 'location', 'bio', 'created_at']
        # The role is chosen at registration and can't be self-promoted afterwards.
        read_only_fields = ['role', 'created_at']


class RegisterSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(
        required=True,
        validators=[UniqueValidator(
            queryset=User.objects.all(),
            lookup='iexact',
            message='A user with this email already exists.',
        )],
    )
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    role     = serializers.ChoiceField(choices=['jobseeker', 'employer'], write_only=True)
    phone    = serializers.CharField(required=False, allow_blank=True, write_only=True)
    location = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model  = User
        fields = ['username', 'email', 'password', 'first_name', 'last_name',
                  'role', 'phone', 'location']

    def validate(self, attrs):
        # Run Django's configured password validators (length, common, numeric, similarity).
        candidate = User(
            username=attrs.get('username', ''),
            email=attrs.get('email', ''),
            first_name=attrs.get('first_name', ''),
            last_name=attrs.get('last_name', ''),
        )
        try:
            validate_password(attrs['password'], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'password': list(exc.messages)})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        role     = validated_data.pop('role')
        phone    = validated_data.pop('phone', '')
        location = validated_data.pop('location', '')
        user = User.objects.create_user(**validated_data)
        UserProfile.objects.create(user=user, role=role, phone=phone, location=location)
        Resume.objects.create(user=user, skills='')
        return user


class ResumeSerializer(serializers.ModelSerializer):
    username    = serializers.CharField(source='user.username', read_only=True)
    skills_list = serializers.SerializerMethodField()

    class Meta:
        model  = Resume
        fields = [
            'id', 'username', 'full_name', 'skills', 'skills_list',
            'experience', 'education', 'certifications',
            'linkedin_url', 'github_url', 'updated_at'
        ]

    def validate_skills(self, value):
        """Trim, drop empties and de-duplicate (case-insensitive) while keeping order."""
        seen, cleaned = set(), []
        for item in value.split(','):
            item = item.strip()
            if item and item.lower() not in seen:
                seen.add(item.lower())
                cleaned.append(item)
        return ', '.join(cleaned)

    def get_skills_list(self, obj):
        return obj.get_skills_list()
