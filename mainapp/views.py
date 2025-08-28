import json
from django.shortcuts import get_object_or_404, redirect,render

from inventoryApi.serializers import CategorySerializer
from .models import InventoryItem, Category,  Customer, BusinessOwner, Notification, SignupToken, Sale, SaleItem
#from .forms import InventoryItemForm, CategoryForm, SaleForm

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, Http404
from django.views.decorators.http import require_POST
from django.db.models import Sum, Count, F
from django.utils import timezone
from datetime import timedelta
from .utils import active_subscription_required


# views for just only serving login 
def login(request):
    """View for handling login"""
    return render(request, 'login.html', {
        'page_title': 'Login',
        'page_subtitle': 'Access your business account'
    })

# views for just only serving signup page with token required
def signup(request, token):
    """View for handling signup with token validation"""
    # Validate token
    email = SignupToken.validate_token(token)
    if not email:
        raise Http404("Invalid or expired signup token")
    
    # If token is valid, render signup page
    return render(request, 'signup.html', {
        'page_title': 'Create Your Account',
        'page_subtitle': 'Set up your business account',
        'email': email,  # Pass email to template for verification
        'token': token   # Pass token to template for API calls
    })

# ✅ Payment success handler
@login_required(login_url='/login')
def payment_success(request):
    business_owner = request.user
    plan_type = request.GET.get('plan', 'yearly')
    
    # Activate subscription based on plan type
    if plan_type == 'monthly':
        business_owner.activate_subscription(duration_days=30)
    else:
        business_owner.activate_subscription(duration_days=365)
    
    return redirect('subscription')

def payment_required(request):
    return render(request, 'payment_required.html')

@login_required(login_url="/login")
@active_subscription_required
def inventory_view(request):
    """View for the inventory management page"""
    business_owner = request.user
    
    # Get top 20 inventory items with category info
    inventory_items = InventoryItem.objects.filter(
        business_owner=business_owner
    ).select_related('category').order_by('-created_at')[:20]
    
    # Get all categories for the business owner
    categories = Category.objects.filter(business_owner=business_owner)
    
    # Calculate stats
    total_items = InventoryItem.objects.filter(business_owner=business_owner).count()
    total_value = InventoryItem.objects.filter(business_owner=business_owner).aggregate(
        total=Sum(F('price') * F('quantity'))
    )['total'] or 0
    low_stock_count = InventoryItem.objects.filter(
        business_owner=business_owner,
        quantity__lte=F('min_stock')
    ).count()
    categories_count = categories.count()
    
    # Prepare initial data for the template
    initial_data = {
        'inventory_items': [
            {
                'id': item.id,
                'name': item.name,
                'sku': item.sku,
                'category': item.category.name if item.category else None,
                'category_id': item.category.id if item.category else None,
                'size': item.size,
                'price': float(item.price),
                'quantity': item.quantity,
                'min_stock': item.min_stock,
                'status': item.status,
                'created_at': item.created_at.isoformat()
            }
            for item in inventory_items
        ],
        'categories': [
            {
                'id': cat.id,
                'name': cat.name,
                'item_count': cat.items.count()
            }
            for cat in categories
        ],
        'stats': {
            'total_items': total_items,
            'total_value': float(total_value),
            'low_stock_count': low_stock_count,
            'categories_count': categories_count
        }
    }
    
    context = {
        'page_title': 'Inventory Management',
        'page_subtitle': 'Manage your product inventory with ease',
        'initial_data': json.dumps(initial_data),
        'csrf_token': request.COOKIES.get('csrftoken', '')
    }
    
    return render(request, 'pages/inventory.html', context)

@login_required(login_url="/login")
@active_subscription_required
def dashboard(request):
    business_owner = request.user
    # Total products
    total_products = InventoryItem.objects.filter(business_owner=business_owner).count()
    # Total sales (sum of all sales)
    total_sales = Sale.objects.filter(business_owner=business_owner).aggregate(total=Sum('total_amount'))['total'] or 0
    # Low stock items
    low_stock_count = InventoryItem.objects.filter(business_owner=business_owner, quantity__lte=F('min_stock')).count()
    # Categories count
    categories_count = Category.objects.filter(business_owner=business_owner).count()
    # Recent products
    recent_products = InventoryItem.objects.filter(business_owner=business_owner).order_by('-created_at')[:5]
    # Recent sales
    recent_sales = Sale.objects.filter(business_owner=business_owner).order_by('-created_at')[:5]
    context = {
        'total_products': total_products,
        'total_sales': float(total_sales),
        'low_stock_count': low_stock_count,
        'categories_count': categories_count,
        'recent_products': recent_products,
        'recent_sales': recent_sales,
    }
    return render(request, 'pages/dashboard.html', context)

@login_required(login_url="/login")
@active_subscription_required
def sales(request):
    business_owner = request.user
    today = timezone.now().date()
    sales_today = Sale.objects.filter(business_owner=business_owner, created_at__date=today)
    # Today's sales total
    today_sales_total = sales_today.aggregate(total=Sum('total_amount'))['total'] or 0
    # Transactions count
    today_transactions = sales_today.count()
    # Items sold today
    items_sold = SaleItem.objects.filter(sale__in=sales_today).aggregate(total=Sum('quantity'))['total'] or 0
    # Avg sale
    avg_sale = today_sales_total / today_transactions if today_transactions else 0
    # Recent sales
    recent_sales = Sale.objects.filter(business_owner=business_owner).order_by('-created_at')[:10]
    context = {
        'today_sales_total': float(today_sales_total),
        'today_transactions': today_transactions,
        'items_sold': items_sold,
        'avg_sale': float(avg_sale),
        'recent_sales': recent_sales,
    }
    return render(request, 'pages/sales.html', context)

@login_required(login_url="/login")
@active_subscription_required
def reports(request):
    business_owner = request.user
    # Total sales
    total_sales = Sale.objects.filter(business_owner=business_owner).aggregate(total=Sum('total_amount'))['total'] or 0
    # Total orders
    total_orders = Sale.objects.filter(business_owner=business_owner).count()
    # Avg order value
    avg_order_value = total_sales / total_orders if total_orders else 0
    # Top product (by quantity sold)
    top_product = SaleItem.objects.filter(sale__business_owner=business_owner)\
        .values('item__name').annotate(total_sold=Sum('quantity')).order_by('-total_sold').first()
    top_product_name = top_product['item__name'] if top_product else '-'
    # Sales trend (last 6 months)
    sales_trend = []
    for i in range(5, -1, -1):
        month = (timezone.now() - timedelta(days=30*i)).strftime('%b')
        month_start = (timezone.now() - timedelta(days=30*i)).replace(day=1)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        month_total = Sale.objects.filter(business_owner=business_owner, created_at__date__gte=month_start, created_at__date__lte=month_end).aggregate(total=Sum('total_amount'))['total'] or 0
        sales_trend.append({'month': month, 'total': float(month_total)})
    # Sales by category
    sales_by_category = SaleItem.objects.filter(sale__business_owner=business_owner)\
        .values('item__category__name').annotate(total=Sum('quantity')).order_by('-total')
    context = {
        'total_sales': float(total_sales),
        'total_orders': total_orders,
        'avg_order_value': float(avg_order_value),
        'top_product': top_product_name,
        'sales_trend': sales_trend,
        'sales_by_category': sales_by_category,
    }
    return render(request, 'pages/reports.html', context)

@login_required(login_url="/login")
def subscription(request):
    from django.conf import settings
    monthly_amount = settings.MONTHLY_SUBSCRIPTION_AMOUNT / 100
    yearly_amount = settings.YEARLY_SUBSCRIPTION_AMOUNT / 100
    paystack_public_key = settings.PAYSTACK_PUBLIC_KEY
    paystack_plans = settings.PAYSTACK_PLANS

    business_owner = request.user
    # Determine subscription status based on actual model fields
    is_active = business_owner.is_subscription_active
    plan_type = 'Premium' if is_active else 'Free'
    
    # Calculate days remaining
    days_remaining = None
    if business_owner.subscription_end_date:
        from datetime import datetime
        now = timezone.now()
        if business_owner.subscription_end_date > now:
            days_remaining = (business_owner.subscription_end_date - now).days
    
    context = {
        'page_title': 'Subscription Management',
        'page_subtitle': 'Manage your subscription plan',
        'subscription_status': {
            'is_active': is_active,
            'plan_type': plan_type,
            'status': business_owner.subscription_status,
            'start_date': business_owner.subscription_start_date,
            'end_date': business_owner.subscription_end_date,
            'days_remaining': days_remaining,
            'features': {
                'inventory_management': True,
                'customer_management': True,
                'sales_tracking': is_active,
                'advanced_reports': is_active,
                'multiple_users': is_active
            }
        },
        'monthly_amount': monthly_amount,
        'yearly_amount': yearly_amount,
        'paystack_public_key': paystack_public_key,
        'paystack_plans': paystack_plans,
    }
    return render(request, 'pages/subscription.html', context)

def landing(request):
    from django.conf import settings
    
    # Convert amounts from kobo to naira for display
    monthly_amount = settings.MONTHLY_SUBSCRIPTION_AMOUNT / 100
    yearly_amount = settings.YEARLY_SUBSCRIPTION_AMOUNT / 100
    
    context = {
        'monthly_amount': monthly_amount,
        'yearly_amount': yearly_amount,
        'paystack_public_key': settings.PAYSTACK_PUBLIC_KEY,
        'paystack_plans': settings.PAYSTACK_PLANS,
        'hourly_amount' : 100,
    }
    
    return render(request, 'landing.html', context)

@login_required(login_url="/login")
@active_subscription_required
def customer_list(request):
    """View for listing and managing customers"""
    return render(request, 'pages/customer.html', {
        'page_title': 'Customer Management',
        'page_subtitle': 'Manage your customers'
    })

# good to go
@login_required(login_url="/login")
@active_subscription_required
def category_list(request):
    """View for listing and managing categories."""
    business_owner = request.user
    
    # Get all categories and annotate with the count of related inventory items.
    # This is the single source of truth for the initial page load.
    categories_queryset = Category.objects.filter(
        business_owner=business_owner
    ).annotate(
        item_count=Count('items')
    ).order_by('-created_at')

    # Serialize the queryset to pass it to JavaScript.
    # Using our DRF serializer ensures the data format is consistent with the API.
    serializer = CategorySerializer(categories_queryset, many=True)
    categories_json = json.dumps(serializer.data)

    return render(request, 'pages/category.html', {
        'page_title': 'Category Management',
        'page_subtitle': 'Manage your product categories',
        'categories': categories_queryset,      # For the initial server-side render by Django templates.
        'categories_json': categories_json, # For initializing the state in client-side JavaScript.
    })

@login_required(login_url="/login")
@active_subscription_required
def inventory_category_view(request, category_id):
    """View for category-specific inventory management page"""
    business_owner = request.user
    
    # Get the specific category
    category = get_object_or_404(Category, id=category_id, business_owner=business_owner)
    
    # Get inventory items for this specific category
    inventory_items = InventoryItem.objects.filter(
        business_owner=business_owner,
        category=category
    ).select_related('category').order_by('-created_at')[:20]
    
    # Get all categories for the business owner (for dropdowns)
    categories = Category.objects.filter(business_owner=business_owner)
    
    # Calculate stats for this category only
    total_items = InventoryItem.objects.filter(business_owner=business_owner, category=category).count()
    total_value = InventoryItem.objects.filter(business_owner=business_owner, category=category).aggregate(
        total=Sum(F('price') * F('quantity'))
    )['total'] or 0
    low_stock_count = InventoryItem.objects.filter(
        business_owner=business_owner,
        category=category,
        quantity__lte=F('min_stock')
    ).count()
    categories_count = categories.count()
    
    # Prepare initial data for the template
    initial_data = {
        'inventory_items': [
            {
                'id': item.id,
                'name': item.name,
                'sku': item.sku,
                'category': item.category.name if item.category else None,
                'category_id': item.category.id if item.category else None,
                'size': item.size,
                'price': float(item.price),
                'quantity': item.quantity,
                'min_stock': item.min_stock,
                'status': item.status,
                'created_at': item.created_at.isoformat()
            }
            for item in inventory_items
        ],
        'categories': [
            {
                'id': cat.id,
                'name': cat.name,
                'item_count': cat.items.count()
            }
            for cat in categories
        ],
        'stats': {
            'total_items': total_items,
            'total_value': float(total_value),
            'low_stock_count': low_stock_count,
            'categories_count': categories_count
        },
        'current_category': {
            'id': category.id,
            'name': category.name,
            'item_count': category.items.count()
        }
    }
    
    context = {
        'page_title': f'{category.name} - Inventory',
        'page_subtitle': f'Manage your {category.name} products',
        'initial_data': initial_data
    }
    
    return render(request, 'pages/inventory_category.html', context)


@login_required(login_url="/login")
def subscription_expired(request):
    return render(request, 'pages/subscription_expired.html')

# for payment successfull unauthenticated
def payment_success_unauthenticated(request, token):
    """
    Shows a success message after payment and before signup.
    Instructs the user to check their email for the signup link.
    """
    signup_token = get_object_or_404(SignupToken, token=token)
    return render(request, 'payment_success_unauth.html', {
        'email': signup_token.email
    })

def unathenticated_payment_verify_page(request):
    return render(request,"unathenticated_payment_verify.html")

def renewal_subscription_success_page(request):
    """
    Renders the subscription renewal success page.
    This page informs the user that their subscription has been renewed.
    """
    return render(request, 'pages/renewal_subscription_success.html')

@login_required(login_url="/login")
def auth_payment_verify_page(request):
    """
    Renders the authenticated payment verification page.
    This page allows logged-in users to verify their renewal payment.
    """
    return render(request, 'pages/auth_payment_verify.html')

# page that waits for webhook confirmation for user
def payment_confirmation_wait(request):
    """
    Renders the page that waits for webhook confirmation after a user pays...
    """
    reference = request.GET.get('reference')
    initial_reference = request.GET.get("initial_reference")
    if not reference:
        return redirect('landing')
    return render(request, 'pages/payment_confirmation_wait.html', {'payment_reference': reference, "initial_reference":initial_reference})


# misc 
@login_required(login_url="/login")
def notifications_list(request):
    notifications = Notification.objects.filter(owner=request.user)
    return render(request, "notifications/list.html", {"notifications": notifications})

@login_required(login_url="/login")
def mark_as_read(request, pk):
    notification = get_object_or_404(Notification, pk=pk, owner=request.user)
    notification.mark_as_read()
    return redirect("notifications_list")

@login_required(login_url="/login")
def mark_all_as_read(request):
    Notification.objects.filter(owner=request.user, is_read=False).delete()
    return redirect("notifications_list")
