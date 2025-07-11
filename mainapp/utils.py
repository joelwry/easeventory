from functools import wraps
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from mainapp.models import BusinessOwner

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
