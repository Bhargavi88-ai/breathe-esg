"""
Accounts models: custom User and Organisation (tenant).

Multi-tenancy design: every piece of data belongs to an Organisation.
Users belong to one Organisation and one Role within it.
"""
import uuid
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class Organisation(models.Model):
    """
    Top-level tenant. Every client company gets their own Organisation.
    All data is scoped to an org — no row ever leaks across tenants.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    # Reporting year this org is currently working on
    active_reporting_year = models.IntegerField(default=2024)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "organisations"

    def __str__(self):
        return self.name


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom user. Email-based auth. Scoped to an Organisation.
    Roles: analyst (review/approve), admin (full access), viewer (read-only).
    """
    ROLE_ANALYST = "analyst"
    ROLE_ADMIN = "admin"
    ROLE_VIEWER = "viewer"
    ROLE_CHOICES = [
        (ROLE_ANALYST, "Analyst"),
        (ROLE_ADMIN, "Admin"),
        (ROLE_VIEWER, "Viewer"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    organisation = models.ForeignKey(
        Organisation,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="users",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_ANALYST)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UserManager()

    class Meta:
        db_table = "users"

    def __str__(self):
        return self.email

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.email
