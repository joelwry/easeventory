from functools import wraps
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

# Decorator that checks if the user is authenticated and has paid
def paid_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.has_paid:
            return redirect('payment_required')  # Redirect to a view that prompts payment
        return view_func(request, *args, **kwargs)
    return wrapper
