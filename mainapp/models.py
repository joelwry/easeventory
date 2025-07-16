from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.crypto import get_random_string
from django.core.validators import MinValueValidator
from django.utils import timezone
import uuid
import hashlib
import time

class BusinessOwner(AbstractUser):
    """Model for business owners who subscribe to the SAAS platform"""
    telephone = models.CharField(max_length=20, unique=True)
    subscription_token = models.CharField(max_length=100, unique=True, null=True, blank=True)
    subscription_status = models.CharField(
        max_length=20,
        choices=[
            ('active', 'Active'),
            ('expired', 'Expired'),
            ('pending', 'Pending'),
        ],
        default='pending'
    )
    subscription_start_date = models.DateTimeField(null=True, blank=True)
    subscription_end_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    business_name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=20)
    address = models.TextField(blank=True)
    
    # Paystack payment tracking
    paystack_customer_code = models.CharField(max_length=100, null=True, blank=True)
    paystack_subscription_code = models.CharField(max_length=100, null=True, blank=True)
    last_payment_reference = models.CharField(max_length=100, null=True, blank=True)
    last_payment_date = models.DateTimeField(null=True, blank=True)
    subscription_plan = models.CharField(
        max_length=20,
        choices=[
            ('monthly', 'Monthly'),
            ('yearly', 'Yearly'),
        ],
        null=True, blank=True
    )

    groups = models.ManyToManyField(
        'auth.Group',
        related_name='business_owner_set',
        blank=True,
        help_text='The groups this user belongs to.',
        verbose_name='groups',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='business_owner_set',
        blank=True,
        help_text='Specific permissions for this user.',
        verbose_name='user permissions',
    )

    class Meta:
        verbose_name = 'Business Owner'
        verbose_name_plural = 'Business Owners'

    def __str__(self):
        return f"{self.business_name} ({self.email})"

    def generate_subscription_token(self):
        """Generate a unique token for subscription verification"""
        token = get_random_string(32)
        self.subscription_token = token
        self.save()
        return token

    def activate_subscription(self, duration_days=30, plan_type='monthly'):
        """Activate subscription for the business owner"""
        self.subscription_status = 'active'
        self.subscription_start_date = timezone.now()
        self.subscription_end_date = timezone.now() + timezone.timedelta(days=duration_days)
        self.subscription_plan = plan_type
        self.save()

    @property
    def is_subscription_active(self):
        """Check if subscription is active"""
        if not self.subscription_end_date:
            return False
        return self.subscription_status == 'active' and timezone.now() <= self.subscription_end_date

    def get_subscription_days_remaining(self):
        """Get days remaining in subscription"""
        if not self.subscription_end_date:
            return 0
        remaining = self.subscription_end_date - timezone.now()
        return max(0, remaining.days)

class Category(models.Model):
    """Model for product categories"""
    name = models.CharField(max_length=100)
    business_owner = models.ForeignKey(BusinessOwner, on_delete=models.CASCADE, related_name='categories')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('name', 'business_owner')
        verbose_name_plural = 'Categories'

    def __str__(self):
        return f"{self.name} ({self.business_owner.username})"

class InventoryItem(models.Model):
    """Model for inventory items"""
    STATUS_CHOICES = [
        ('in_stock', 'In Stock'),
        ('low_stock', 'Low Stock'),
        ('out_of_stock', 'Out of Stock'),
    ]

    business_owner = models.ForeignKey(BusinessOwner, on_delete=models.CASCADE, related_name='inventory_items')
    name = models.CharField(max_length=200)
    sku = models.CharField(max_length=50, unique=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='items')
    size = models.CharField(max_length=50, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    quantity = models.PositiveIntegerField(default=0)
    min_stock = models.PositiveIntegerField(default=10)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='in_stock')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.sku} => {self.business_owner.username})"

    def save(self, *args, **kwargs):
        """Override save to automatically generate SKU and update status"""
        if not self.sku:
            self.generate_sku()
        self.update_status()
        super().save(*args, **kwargs)

    def generate_sku(self):
        """Generate a unique SKU for the item"""
        prefix = self.name[:3].upper()
        random_suffix = get_random_string(6).upper()
        self.sku = f"{prefix}-{random_suffix}"

    def update_status(self):
        """Update item status based on quantity"""
        if self.quantity <= 0:
            self.status = 'out_of_stock'
        elif self.quantity <= self.min_stock:
            self.status = 'low_stock'
        else:
            self.status = 'in_stock'

    def add_stock(self, quantity):
        """Add stock to inventory"""
        self.quantity += quantity
        self.save()

    def remove_stock(self, quantity):
        """Remove stock from inventory"""
        if self.quantity >= quantity:
            self.quantity -= quantity
            self.save()
            return True
        return False

class Customer(models.Model):
    """Model for business customers"""
    business_owner = models.ForeignKey(BusinessOwner, on_delete=models.CASCADE, related_name='customers')
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    class Meta:
        unique_together = ('business_owner', 'email', 'phone')

class Sale(models.Model):
    """Model for sales transactions"""
    business_owner = models.ForeignKey(BusinessOwner, on_delete=models.CASCADE, related_name='sales')
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='purchases')
    items = models.ManyToManyField(InventoryItem, through='SaleItem')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Sale #{self.id} - {self.customer.first_name} {self.customer.last_name}"

class SaleItem(models.Model):
    """Model for items in a sale"""
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE)
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    price_at_sale = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.item.name} x {self.quantity}"

    def save(self, *args, **kwargs):
        """Override save to update inventory quantity"""
        if not self.pk:  # Only on creation
            self.item.remove_stock(self.quantity)
        super().save(*args, **kwargs)

class SignupToken(models.Model):
    email = models.EmailField(unique=True)
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    duration_days = models.PositiveIntegerField(null=True, blank=True, help_text="Subscription duration in days (optional)")
    
    def save(self, *args, **kwargs):
        if not self.token:
            # Generate a unique token using email, timestamp, and a secret key
            import time, hashlib
            from django.utils import timezone
            timestamp = str(int(time.time()))
            secret_key = "EazyInventory2024"  # This should be in settings.py in production
            raw_token = f"{self.email}{timestamp}{secret_key}"
            self.token = hashlib.sha256(raw_token.encode()).hexdigest()
            # Set expiration to duration_days or 7 days from creation
            if self.duration_days:
                self.expires_at = timezone.now() + timezone.timedelta(days=self.duration_days)
            else:
                self.expires_at = timezone.now() + timezone.timedelta(days=7)
        super().save(*args, **kwargs)
    
    @property
    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at
    
    @classmethod
    def generate_token(cls, email):
        """Generate a new token for an email"""
        # Delete any existing tokens for this email
        cls.objects.filter(email=email).delete()
        return cls.objects.create(email=email)
    
    @classmethod
    def validate_token(cls, token):
        """Validate a token and return the associated email if valid"""
        try:
            token_obj = cls.objects.get(token=token)
            if token_obj.is_valid:
                return token_obj.email
        except cls.DoesNotExist:
            pass
        return None

class PaymentTransaction(models.Model):
    reference = models.CharField(max_length=100, unique=True)
    email = models.EmailField()  # For signups, before user exists
    user = models.ForeignKey(
        'BusinessOwner', on_delete=models.SET_NULL, null=True, blank=True
    )
    amount = models.PositiveIntegerField()
    status = models.CharField(max_length=20)  # e.g., 'success', 'failed', 'pending'
    transaction_type = models.CharField(max_length=20)  # 'signup' or 'renewal'
    metadata = models.JSONField(null=True, blank=True)
    processed_at = models.DateTimeField(auto_now_add=True)
    signup_token = models.ForeignKey(
        'SignupToken', on_delete=models.SET_NULL, null=True, blank=True
    )

    def __str__(self):
        return f"{self.reference} ({self.status})"

