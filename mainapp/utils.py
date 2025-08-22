from functools import wraps
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from mainapp.models import BusinessOwner
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
import hashlib
import hmac

# Decorator that checks if the user is authenticated and has paid
def paid_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.has_paid:
            return redirect('payment_required')  # Redirect to a view that prompts payment
        return view_func(request, *args, **kwargs)
    return wrapper

# Decorator that checks if the user is authenticated and has an active subscription
def active_subscription_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not isinstance(user, BusinessOwner) or not user.is_subscription_active:
            return redirect('subscription_expired')  # You should have a view named 'subscription_expired'
        return view_func(request, *args, **kwargs)
    return wrapper

# Email utility functions
def send_signup_token_email(email, token, duration_days=None):
    """Send signup token email to new business owner"""
    subject = "Welcome to EasyBook - Complete Your Registration"
    
    # Build signup URL
    signup_url = f"{settings.SITE_URL}/signup/{token}/"
    
    # Determine plan type based on duration
    if duration_days:
        if duration_days >= 365:
            plan_type = "Yearly"
        elif duration_days >= 180:
            plan_type = "6 Months"
        elif duration_days >= 30:
            plan_type = "Monthly"
        else:
            plan_type = "Trial"
    else:
        plan_type = "Standard"
    
    context = {
        'email': email,
        'signup_url': signup_url,
        'plan_type': plan_type,
        'duration_days': duration_days,
        'site_url': settings.SITE_URL
    }
    
    html_message = render_to_string('emails/signup_token.html', context)
    plain_message = render_to_string('emails/signup_token.txt', context)
    
    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            html_message=html_message,
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Failed to send signup email: {e}")
        return False

def send_payment_confirmation_email(business_owner):
    """Send payment confirmation email"""
    subject = "Payment Confirmed - Your EasyBook Subscription is Active"
    
    context = {
        'business_owner': business_owner,
        'subscription_end_date': business_owner.subscription_end_date,
        'days_remaining': business_owner.get_subscription_days_remaining(),
        'site_url': settings.SITE_URL
    }
    
    html_message = render_to_string('emails/payment_confirmation.html', context)
    plain_message = render_to_string('emails/payment_confirmation.txt', context)
    
    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[business_owner.email],
            html_message=html_message,
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Failed to send payment confirmation email: {e}")
        return False

def send_subscription_reminder_email(business_owner, days_remaining):
    """Send subscription renewal reminder"""
    subject = f"Subscription Expiring Soon - {days_remaining} Days Remaining"
    
    context = {
        'business_owner': business_owner,
        'days_remaining': days_remaining,
        'subscription_end_date': business_owner.subscription_end_date,
        'site_url': settings.SITE_URL
    }
    
    html_message = render_to_string('emails/subscription_reminder.html', context)
    plain_message = render_to_string('emails/subscription_reminder.txt', context)
    
    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[business_owner.email],
            html_message=html_message,
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Failed to send subscription reminder email: {e}")
        return False

def send_welcome_email(business_owner):
    """Send welcome email after successful signup"""
    subject = "Welcome to EasyBook - Your Account is Ready!"
    
    context = {
        'business_owner': business_owner,
        'subscription_status': business_owner.subscription_status,
        'subscription_end_date': business_owner.subscription_end_date,
        'site_url': settings.SITE_URL
    }
    
    html_message = render_to_string('emails/welcome.html', context)
    plain_message = render_to_string('emails/welcome.txt', context)
    
    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[business_owner.email],
            html_message=html_message,
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Failed to send welcome email: {e}")
        return False


# Paystack webhook verification
def verify_paystack_webhook(request):
    """Verify Paystack webhook signature"""
    try:
        # Get the signature from headers
        signature = request.headers.get('X-Paystack-Signature')
        if not signature:
            return False
        
        # Get the request body
        body = request.body
        
        # Verify using your Paystack secret key
        secret_key = settings.PAYSTACK_SECRET_KEY
        computed_signature = hmac.new(
            secret_key.encode('utf-8'),
            body,
            hashlib.sha512
        ).hexdigest()
        
        return hmac.compare_digest(computed_signature, signature)
    except Exception as e:
        print(f"Webhook verification failed: {e}")
        return False
