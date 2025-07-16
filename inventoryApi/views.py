from django.shortcuts import get_object_or_404

from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAuthenticated, AllowAny
from rest_framework.decorators import api_view, permission_classes, authentication_classes, action
from rest_framework.authentication import TokenAuthentication
from django.views.decorators.csrf import csrf_exempt
from .serializers import InventoryItemSerializer, SaleSerializer, CustomerSerializer, CategorySerializer, UserSerializer
from django.http import HttpResponseBadRequest, JsonResponse, HttpResponse
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate,login
from django.contrib.auth.models import User
from mainapp.models import Customer, SaleItem, SignupToken, BusinessOwner
from mainapp.models import InventoryItem,Sale
from django.db.models import F, Sum
from mainapp.models import Category
from datetime import timedelta
from django.utils import timezone
import csv
from mainapp.utils import active_subscription_required, verify_paystack_webhook, send_signup_token_email, send_payment_confirmation_email
import requests
import json
from rest_framework import status
import logging
import os
from django.conf import settings
from mainapp.models import PaymentTransaction  # Add this import
from rest_framework.views import APIView  # For PaystackWebhook2

logger = logging.getLogger(__name__)

# Paystack API configuration from settings
PAYSTACK_SECRET_KEY = settings.PAYSTACK_SECRET_KEY
PAYSTACK_PUBLIC_KEY = settings.PAYSTACK_PUBLIC_KEY

# Paystack plan codes from settings
PAYSTACK_PLANS = settings.PAYSTACK_PLANS

# Subscription amounts from settings
MONTHLY_SUBSCRIPTION_AMOUNT = settings.MONTHLY_SUBSCRIPTION_AMOUNT
YEARLY_SUBSCRIPTION_AMOUNT = settings.YEARLY_SUBSCRIPTION_AMOUNT

# ✅ Inventory view with staff-only delete


# ✅ Public and private inventory list
@csrf_exempt
@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([AllowAny])  # GET is public; POST checks request.user below
def inventory_list_api(request):
    """API endpoint for listing inventory items with pagination and filtering, and returning filtered stats"""
    business_owner = request.user
    page = int(request.GET.get('page', 1))
    per_page = int(request.GET.get('per_page', 20))
    search = request.GET.get('search', '')
    category_id = request.GET.get('category')
    stock_status = request.GET.get('status')
    
    # Base queryset
    queryset = InventoryItem.objects.filter(business_owner=business_owner)
    
    # Apply filters
    if search:
        queryset = queryset.filter(name__icontains=search)
    if category_id:
        queryset = queryset.filter(category_id=category_id)
    if stock_status:
        if stock_status == 'low-stock':
            queryset = queryset.filter(quantity__lte=F('min_stock'))
        elif stock_status == 'out-of-stock':
            queryset = queryset.filter(quantity=0)
        elif stock_status == 'in-stock':
            queryset = queryset.filter(quantity__gt=F('min_stock'))
    
    # Calculate total count before pagination
    total_count = queryset.count()
    
    # Apply pagination
    start = (page - 1) * per_page
    end = start + per_page
    items = queryset.select_related('category')[start:end]
    
    # Serialize data
    serializer = InventoryItemSerializer(items, many=True)

    # Filtered stats
    stats = {
        'total_items': queryset.count(),
        'total_value': float(queryset.aggregate(total=Sum(F('price') * F('quantity')))['total'] or 0),
        'low_stock_count': queryset.filter(quantity__lte=F('min_stock')).count(),
        'categories_count': queryset.values('category').distinct().count()
    }
    
    return Response({
        'items': serializer.data,
        'total_count': total_count,
        'page': page,
        'per_page': per_page,
        'total_pages': (total_count + per_page - 1) // per_page,
        'stats': stats
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@active_subscription_required
def add_inventory_item(request):
    """API endpoint for adding a new inventory item"""
    business_owner = request.user
    data = request.data.copy()
    data['business_owner'] = business_owner.id
    
    serializer = InventoryItemSerializer(data=data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['PUT'])
@permission_classes([IsAuthenticated])
@active_subscription_required
def update_inventory_item(request, item_id):
    """API endpoint for updating an inventory item"""
    business_owner = request.user
    item = get_object_or_404(InventoryItem, id=item_id, business_owner=business_owner)
    
    serializer = InventoryItemSerializer(item, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
@active_subscription_required
def delete_inventory_item(request, item_id):
    """API endpoint for deleting an inventory item"""
    business_owner = request.user
    item = get_object_or_404(InventoryItem, id=item_id, business_owner=business_owner)
    
    item.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@active_subscription_required
def adjust_stock(request, item_id):
    """API endpoint for adjusting stock quantity"""
    business_owner = request.user
    item = get_object_or_404(InventoryItem, id=item_id, business_owner=business_owner)
    
    quantity_change = request.data.get('quantity_change', 0)
    if not isinstance(quantity_change, int):
        return Response(
            {'error': 'Quantity change must be an integer'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    new_quantity = item.quantity + quantity_change
    if new_quantity < 0:
        return Response(
            {'error': 'Insufficient stock'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    item.quantity = new_quantity
    item.save()
    
    serializer = InventoryItemSerializer(item)
    return Response(serializer.data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@active_subscription_required
def inventory_stats(request):
    """API endpoint for getting inventory statistics"""
    business_owner = request.user
    
    stats = {
        'total_items': InventoryItem.objects.filter(business_owner=business_owner).count(),
        'total_value': float(InventoryItem.objects.filter(business_owner=business_owner).aggregate(
            total=Sum(F('price') * F('quantity'))
        )['total'] or 0),
        'low_stock_count': InventoryItem.objects.filter(
            business_owner=business_owner,
            quantity__lte=F('min_stock')
        ).count(),
        'categories_count': Category.objects.filter(business_owner=business_owner).count()
    }
    
    return Response(stats)

# NOT USED 4 NOW HENCE option for removing this view 
class InventoryItemViewSet(viewsets.ModelViewSet):
    serializer_class = InventoryItemSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        return InventoryItem.objects.filter(business_owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(business_owner=self.request.user)

# User-specific sales records
class SaleViewSet(viewsets.ModelViewSet):
    serializer_class = SaleSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Sale.objects.filter(business_owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(business_owner=self.request.user)

    def dispatch(self, request, *args, **kwargs):
        # Apply subscription check to all methods
        return active_subscription_required(super().dispatch)(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        data = request.data
        business_owner = request.user
        customer_id = data.get('customer')
        items = data.get('items', [])
        total_amount = data.get('total_amount')
        payment_method = data.get('payment_method')

        # Validate customer
        customer = get_object_or_404(Customer, id=customer_id, business_owner=business_owner)

        # Validate items and stock
        sale_items = []
        for item in items:
            item_id = item.get('item_id')
            quantity = int(item.get('quantity', 0))
            price_at_sale = item.get('price_at_sale')
            inventory_item = get_object_or_404(InventoryItem, id=item_id, business_owner=business_owner)
            if inventory_item.quantity < quantity:
                return Response({
                    'error': f'Not enough stock for {inventory_item.name}. Available: {inventory_item.quantity}, Requested: {quantity}'
                }, status=status.HTTP_400_BAD_REQUEST)
            sale_items.append((inventory_item, quantity, price_at_sale))

        # Create Sale
        sale = Sale.objects.create(
            business_owner=business_owner,
            customer=customer,
            total_amount=total_amount
        )

        # Create SaleItems (SaleItem.save() will deduct inventory)
        for inventory_item, quantity, price_at_sale in sale_items:
            sale_item = sale.saleitem_set.create(
                item=inventory_item,
                quantity=quantity,
                price_at_sale=price_at_sale
            )

        serializer = self.get_serializer(sale)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

@csrf_exempt
def paystack_callback(request):
    # This view will handle Paystack payment verification webhook or callback
    # For simplicity, assume payment is successful and set has_paid to True
    if request.method == 'POST':
        user = request.user
        if user.is_authenticated:
            if hasattr(user, 'profile'):
                user.profile.has_paid = True
                user.profile.save()
            else:
                user.has_paid = True
                user.save()
            return JsonResponse({'status': 'success'})
        else:
            return JsonResponse({'error': 'User not authenticated'}, status=401)
    return HttpResponseBadRequest("Invalid request method.")

# Customer API Views
class CustomerViewSet(viewsets.ModelViewSet):
    serializer_class = CustomerSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Customer.objects.filter(business_owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(business_owner=self.request.user)

    def dispatch(self, request, *args, **kwargs):
        # Apply subscription check to all methods
        return active_subscription_required(super().dispatch)(request, *args, **kwargs)

@api_view(['GET', 'POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
@active_subscription_required
def customer_list_api(request):
    if request.method == 'GET':
        customers = Customer.objects.filter(business_owner=request.user)
        serializer = CustomerSerializer(customers, many=True)
        return Response(serializer.data)
    
    elif request.method == 'POST':
        serializer = CustomerSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(business_owner=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['PUT', 'DELETE'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
@active_subscription_required
def customer_detail_api(request, customer_id):
    customer = get_object_or_404(Customer, id=customer_id, business_owner=request.user)
    
    if request.method == 'PUT':
        serializer = CustomerSerializer(customer, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        customer.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

# Category API Views
class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Category.objects.filter(business_owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(business_owner=self.request.user)

    def dispatch(self, request, *args, **kwargs):
        # Apply subscription check to all methods
        return active_subscription_required(super().dispatch)(request, *args, **kwargs)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
@active_subscription_required
def category_list_count(request):
    categories = Category.objects.filter(business_owner=request.user)
    category_formatted =  [
            {
                'id': cat.id,
                'name': cat.name,
                'item_count': cat.items.count()
            }
            for cat in categories
        ]
    print(category_formatted)
    return Response(category_formatted)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@active_subscription_required
def category_inventory_stats(request, category_id):
    """API endpoint for getting inventory statistics for a specific category"""
    business_owner = request.user
    category = get_object_or_404(Category, id=category_id, business_owner=business_owner)

    stats = {
        'total_items': InventoryItem.objects.filter(business_owner=business_owner, category=category).count(),
        'total_value': float(InventoryItem.objects.filter(business_owner=business_owner, category=category).aggregate(
            total=Sum(F('price') * F('quantity'))
        )['total'] or 0),
        'low_stock_count': InventoryItem.objects.filter(
            business_owner=business_owner,
            category=category,
            quantity__lte=F('min_stock')
        ).count(),
        'categories_count': 1  # Only this category
    }
    return Response(stats)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
@active_subscription_required
def category_inventory_list_api(request, category_id):
    """API endpoint for listing inventory items for a specific category with pagination and stats"""
    business_owner = request.user
    page = int(request.GET.get('page', 1))
    per_page = int(request.GET.get('per_page', 20))
    search = request.GET.get('search', '')
    stock_status = request.GET.get('status')

    # Get the category
    category = get_object_or_404(Category, id=category_id, business_owner=business_owner)

    # Base queryset
    queryset = InventoryItem.objects.filter(business_owner=business_owner, category=category)

    # Apply filters
    if search:
        queryset = queryset.filter(name__icontains=search)
    if stock_status:
        if stock_status == 'low-stock':
            queryset = queryset.filter(quantity__lte=F('min_stock'))
        elif stock_status == 'out-of-stock':
            queryset = queryset.filter(quantity=0)
        elif stock_status == 'in-stock':
            queryset = queryset.filter(quantity__gt=F('min_stock'))

    # Calculate total count before pagination
    total_count = queryset.count()

    # Apply pagination
    start = (page - 1) * per_page
    end = start + per_page
    items = queryset.select_related('category')[start:end]

    # Serialize data
    serializer = InventoryItemSerializer(items, many=True)

    # Category-specific stats (filtered)
    stats = {
        'total_items': queryset.count(),
        'total_value': float(queryset.aggregate(total=Sum(F('price') * F('quantity')))['total'] or 0),
        'low_stock_count': queryset.filter(quantity__lte=F('min_stock')).count(),
        'categories_count': 1
    }

    return Response({
        'items': serializer.data,
        'total_count': total_count,
        'page': page,
        'per_page': per_page,
        'total_pages': (total_count + per_page - 1) // per_page,
        'stats': stats
    })

# ✅ Business Owner Account setup page : Good 2go
@api_view(['POST'])
@permission_classes([AllowAny])
def signup_api(request):
    """API endpoint for user signup"""
    token = request.data.get('token')
    email = request.data.get('email')
    password = request.data.get('password')
    business_name = request.data.get('business_name')
    phone_number = request.data.get('phone_number')
    address = request.data.get('address')
    
    # Validate token and email match
    token_email = SignupToken.validate_token(token)
    if not token_email or token_email != email:
        return Response(
            {'error': 'Invalid or expired token'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check if user already exists
    if BusinessOwner.objects.filter(email=email).exists():
        return Response(
            {'error': 'User with this email already exists'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Get the signup token to access duration_days
        signup_token = SignupToken.objects.get(token=token)
        
        # Create business owner directly
        business_owner = BusinessOwner.objects.create_user(
            username=email,  # Use email as username
            email=email,
            password=password,
            business_name=business_name,
            telephone=phone_number,
            address=address
        )
        
        # Set subscription based on token duration
        if signup_token.duration_days and signup_token.duration_days >= 30:
            # If duration is at least 30 days, activate subscription
            business_owner.subscription_status = 'active'
            business_owner.subscription_start_date = timezone.now()
            business_owner.subscription_end_date = timezone.now() + timezone.timedelta(days=signup_token.duration_days)
        else:
            # If duration is less than 30 days or not set, set to pending
            business_owner.subscription_status = 'pending'
            business_owner.subscription_start_date = None
            business_owner.subscription_end_date = None
        
        # Generate subscription token
        business_owner.generate_subscription_token()
        business_owner.save()
        
        # Mark signup token as used
        signup_token.is_used = True
        signup_token.save()
        
        # Generate auth token
        token = Token.objects.create(user=business_owner)
        
        return Response({
            'token': token.key,
            'user': UserSerializer(business_owner).data,
            'business_owner': {
                'business_name': business_owner.business_name,
                'phone_number': business_owner.phone_number,
                'address': business_owner.address,
                'subscription_status': business_owner.subscription_status,
                'subscription_end_date': business_owner.subscription_end_date.isoformat() if business_owner.subscription_end_date else None
            }
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )

@api_view(['POST'])
@permission_classes([AllowAny])
def login_api(request):
    """API endpoint for user login"""
    email = request.data.get('email')
    password = request.data.get('password')
    
    if not email or not password:
        return Response(
            {'error': 'Please provide both email and password'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Authenticate user
    user = authenticate(username=email, password=password)
    
    if not user:
        return Response(
            {'error': 'Invalid credentials'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    # Get or create token
    token, _ = Token.objects.get_or_create(user=user)
    
    # Get business owner details
    try:
        business_owner = BusinessOwner.objects.get(email=user.email)
        business_data = {
            'business_name': business_owner.business_name,
            'phone_number': business_owner.phone_number,
            'address': business_owner.address
        }
    except BusinessOwner.DoesNotExist:
        business_data = None
    
    login(request, user) # django session id for views quick access 

    return Response({
        'token': token.key,
        'user': UserSerializer(user).data,
        'business_owner': business_data
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@active_subscription_required
def analytics_data(request):
    business_owner = request.user
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
    return Response({
        'sales_trend': sales_trend,
        'sales_by_category': list(sales_by_category)
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@active_subscription_required
def export_sales_csv(request):
    business_owner = request.user
    sales = Sale.objects.filter(business_owner=business_owner).order_by('-created_at')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="sales_export.csv"'
    writer = csv.writer(response)
    writer.writerow(['Sale ID', 'Date', 'Customer', 'Total Amount', 'Items'])
    for sale in sales:
        items = "; ".join([f"{si.item.name} x{si.quantity}" for si in sale.saleitem_set.all()])
        writer.writerow([sale.id, sale.created_at.strftime('%Y-%m-%d %H:%M'), f"{sale.customer.first_name} {sale.customer.last_name}", sale.total_amount, items])
    return response

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@active_subscription_required
def export_inventory_csv(request):
    business_owner = request.user
    inventory = InventoryItem.objects.filter(business_owner=business_owner).order_by('name')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="inventory_export.csv"'
    writer = csv.writer(response)
    writer.writerow(['Item ID', 'Name', 'Category', 'SKU', 'Price', 'Quantity', 'Min Stock', 'Status', 'Created At'])
    for item in inventory:
        writer.writerow([
            item.id, item.name, item.category.name if item.category else '', item.sku, item.price, item.quantity, item.min_stock, item.status, item.created_at.strftime('%Y-%m-%d %H:%M')
        ])
    return response

# Paystack Payment Endpoints
@api_view(['POST'])
@permission_classes([AllowAny])
def initialize_payment(request):
    """Initialize payment for new signup from landing page"""
    try:
        data = request.data
        email = data.get('email')
        plan_type = data.get('plan_type', 'yearly')  # monthly or yearly
        
        if not email:
            return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Create signup token with duration based on plan
        duration_days = 365 if plan_type == 'yearly' else 30
        
        # Generate signup token
        signup_token = SignupToken.generate_token(email)
        signup_token.duration_days = duration_days
        # signup_token.save()
        
        amount = YEARLY_SUBSCRIPTION_AMOUNT if plan_type == 'yearly' else MONTHLY_SUBSCRIPTION_AMOUNT
        plan = PAYSTACK_PLANS.get(plan_type)
        # Initialize Paystack 
        paystack_data = {
            'email': email,
            'amount': amount,
            'plan':plan,
            'callback_url': f"{request.build_absolute_uri('/')}payment/verify/",
            'metadata': {
                'email': email,
                'plan_type': plan_type,
                'signup_token': signup_token.token,
                'duration_days': duration_days
            }
        }
        
        # Make request to Paystack
        headers = {
            'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}',
            'Content-Type': 'application/json'
        }
        
        response = requests.post(
            'https://api.paystack.co/transaction/initialize',
            headers=headers,
            json=paystack_data
        )

        if response.status_code == 200:
            paystack_response = response.json()
            print("PAYSTACK RESPONSE ON INITIALIZING PAYMENT")
            print(paystack_response)
            return Response({
                'authorization_url': paystack_response['data']['authorization_url'],
                'reference': paystack_response['data']['reference'],
                'signup_token': signup_token.token,
                "amount": amount, 
                "plan_code": plan

            })
        else:
            return Response({'error': 'Failed to initialize payment'}, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([AllowAny])
def initialize_renewal_payment(request):
    """Initialize payment for subscription renewal"""
    try:
        data = request.data
        plan_type = data.get('plan_type', 'yearly')
        
        if not request.user.is_authenticated:
            return Response({'error': 'User must be authenticated'}, status=status.HTTP_401_UNAUTHORIZED)
        
        business_owner = request.user
        
        # Initialize Paystack payment
        paystack_data = {
            'email': business_owner.email,
            'amount': YEARLY_SUBSCRIPTION_AMOUNT if plan_type == 'yearly' else MONTHLY_SUBSCRIPTION_AMOUNT,  # Amount in kobo
            'plan': PAYSTACK_PLANS.get(plan_type),
            'callback_url': f"{request.build_absolute_uri('/')}payment/verify/",
            'metadata': {
                'email': business_owner.email,
                'plan_type': plan_type,
                'business_owner_id': business_owner.id,
                'is_renewal': True
            }
        }
        
        # Make request to Paystack
        headers = {
            'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}',
            'Content-Type': 'application/json'
        }
        
        response = requests.post(
            'https://api.paystack.co/transaction/initialize',
            headers=headers,
            json=paystack_data
        )
        
        if response.status_code == 200:
            paystack_response = response.json()
            return Response({
                'authorization_url': paystack_response['data']['authorization_url'],
                'reference': paystack_response['data']['reference']
            })
        else:
            return Response({'error': 'Failed to initialize payment'}, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def paystack_webhook(request):
    """Handle Paystack webhook for payment confirmations"""
    try:
        # Verify webhook signature
        if not verify_paystack_webhook(request):
            return Response({'error': 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Parse webhook data
        webhook_data = json.loads(request.body)
        event = webhook_data.get('event')
        data = webhook_data.get('data', {})
        
        if event == 'charge.success':
            # Payment was successful
            reference = data.get('reference')
            metadata = data.get('metadata', {})
            email = metadata.get('email')
            plan_type = metadata.get('plan_type')
            signup_token = metadata.get('signup_token')
            business_owner_id = metadata.get('business_owner_id')
            is_renewal = metadata.get('is_renewal', False)
            
            if is_renewal and business_owner_id:
                # Handle subscription renewal
                try:
                    business_owner = BusinessOwner.objects.get(id=business_owner_id)
                    duration_days = 365 if plan_type == 'yearly' else 30
                    
                    # Update subscription
                    business_owner.activate_subscription(duration_days=duration_days, plan_type=plan_type)
                    business_owner.last_payment_reference = reference
                    business_owner.last_payment_date = timezone.now()
                    business_owner.save()
                    
                    # Send confirmation email
                    send_payment_confirmation_email(business_owner)
                    
                    logger.info(f"Subscription renewed for {business_owner.email}")
                    
                except BusinessOwner.DoesNotExist:
                    logger.error(f"Business owner not found: {business_owner_id}")
                    
            elif signup_token:
                # Handle new signup payment
                try:
                    # Verify signup token exists and is valid
                    token_obj = SignupToken.objects.get(token=signup_token, email=email)
                    
                    # Send signup token email
                    duration_days = metadata.get('duration_days', 30)
                    send_signup_token_email(email, signup_token, duration_days)
                    
                    logger.info(f"Signup token sent to {email}")
                    
                except SignupToken.DoesNotExist:
                    logger.error(f"Signup token not found: {signup_token}")
        
        elif event == 'subscription.create':
            # Subscription was created
            subscription_code = data.get('subscription_code')
            customer_code = data.get('customer', {}).get('customer_code')
            email = data.get('customer', {}).get('email')
            
            # Update business owner with subscription details
            try:
                business_owner = BusinessOwner.objects.get(email=email)
                business_owner.paystack_subscription_code = subscription_code
                business_owner.paystack_customer_code = customer_code
                business_owner.save()
                
                logger.info(f"Subscription created for {email}")
                
            except BusinessOwner.DoesNotExist:
                logger.error(f"Business owner not found for subscription: {email}")
        
        elif event == 'subscription.disable':
            # Subscription was disabled/cancelled
            subscription_code = data.get('subscription_code')
            
            try:
                business_owner = BusinessOwner.objects.get(paystack_subscription_code=subscription_code)
                business_owner.subscription_status = 'expired'
                business_owner.save()
                
                logger.info(f"Subscription disabled for {business_owner.email}")
                
            except BusinessOwner.DoesNotExist:
                logger.error(f"Business owner not found for subscription: {subscription_code}")
        
        return Response({'status': 'success'})
        
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET','POST'])
@permission_classes([AllowAny])
def verify_payment(request):
    """Verify payment status (for callback) with robust anti-fraud and idempotency logic"""
    try:
        if request.method == 'POST':
            reference = request.data.get('reference')
        elif request.method == 'GET':
            reference = request.GET.get('reference')
        else:
            return Response({'error': 'Invalid method'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

        if not reference:
            return Response({'error': 'Reference is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Check if this reference has already been processed
        if PaymentTransaction.objects.filter(reference=reference, status='success').exists():
            return Response({'status': 'already_processed', 'message': 'This payment reference has already been processed.'})

        # Verify with Paystack
        headers = {
            'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}',
            'Content-Type': 'application/json'
        }
        response = requests.get(
            f'https://api.paystack.co/transaction/verify/{reference}',
            headers=headers
        )

        if response.status_code != 200:
            return Response({'error': 'Failed to verify payment with Paystack'}, status=status.HTTP_400_BAD_REQUEST)
        verification_data = response.json()
        print("PAYSTACK VERIFICATION FROM REFERENCE SENT")
        print(verification_data)

        paystack_status = verification_data['data']['status']
        metadata = verification_data['data'].get('metadata', {})
        email = metadata.get('email') or verification_data['data'].get('customer', {}).get('email')
        plan_type = metadata.get('plan_type')
        signup_token = metadata.get('signup_token')
        business_owner_id = metadata.get('business_owner_id')
        is_renewal = metadata.get('is_renewal', False)
        amount = verification_data['data'].get('amount')
        # Default transaction_type
        transaction_type = 'renewal' if is_renewal else 'signup'
        user = None
        signup_token_obj = None
        # Only process if successful

        if not email:
            return Response({'error': 'No email found in payment metadata or customer info. Cannot create signup token. Contact Admin to rectify if you feel this is an error'}, status=status.HTTP_400_BAD_REQUEST)

        if paystack_status == 'success':
            if is_renewal and business_owner_id:
                try:
                    user = BusinessOwner.objects.get(id=business_owner_id)
                    duration_days = 365 if plan_type == 'yearly' else 30
                    user.activate_subscription(duration_days=duration_days, plan_type=plan_type)
                    user.last_payment_reference = reference
                    user.last_payment_date = timezone.now()
                    user.save()
                    send_payment_confirmation_email(user)
                except BusinessOwner.DoesNotExist:
                    return Response({'error': 'Business owner not found'}, status=status.HTTP_400_BAD_REQUEST)
            
            elif signup_token:
                try:
                    signup_token_obj = SignupToken.objects.get(token=signup_token, email=email)
                    
                    if signup_token_obj.is_used:
                        return Response({'error': 'Signup token already used to create account '}, status=status.HTTP_400_BAD_REQUEST)
                    
                    if signup_token_obj : 
                        return Response({
                            "error":"A token has previously been generated ...consult admin if your email was not delivered to your inbox"
                        }, status = status.HTTP_400_BAD_REQUEST)
                    
                except SignupToken.DoesNotExist:
                    
                    duration_days = metadata.get('duration_days', 30)

                    signup_token_obj = SignupToken.objects.create(token=signup_token, email=email,duration_days=duration_days)
                    signup_token_obj.save()
                    
                    # Record transaction
                    PaymentTransaction.objects.create(
                        reference=reference,
                        email=email,
                        amount=amount,
                        status='success',
                        transaction_type=transaction_type,
                        metadata=metadata,
                        signup_token=signup_token_obj
                    )

                    # send email to user
                    send_signup_token_email(email, signup_token, duration_days)
                    return Response({'error': 'Signup token and link to create your account has successfully been generated for you.. check your email otherwise confirm from admin'}, status=status.HTTP_201_CREATED)

            else:
                # No valid action found
                print("NO SIGNUP TOKEN FOUND even though PAYMENT WAS SUCCESSFULL")
                duration_days = metadata.get('duration_days', 30)

                signup_token_obj = SignupToken.objects.create(email=email,duration_days=duration_days)
                signup_token_obj.save()
                
                # Record transaction
                PaymentTransaction.objects.create(
                    reference=reference,
                    email=email,
                    amount=amount,
                    status='success',
                    transaction_type=transaction_type,
                    metadata=metadata,
                    signup_token=signup_token_obj
                )

                # send email to user
                send_signup_token_email(email, signup_token_obj.token, duration_days)
                return Response({'error': 'Signup token Generated and link to create your account has successfully been sent to your mail.. Having issue with your mail get details from admin based off email you used during subscription'}, status=status.HTTP_201_CREATED)

        else:
            # Record failed transaction
            PaymentTransaction.objects.create(
                reference=reference,
                email=email,
                #user=user,
                amount=amount,
                status=paystack_status,
                transaction_type=transaction_type,
                metadata=metadata,
                signup_token=signup_token_obj
            )
            return Response({'status': 'failed', 'message': 'Payment verification failed.'})
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class PaystackWebhook2(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    def post(self, request):
        try:
            if not verify_paystack_webhook(request):
                return Response({'error': 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)
            webhook_data = json.loads(request.body)
            event = webhook_data.get('event')
            data = webhook_data.get('data', {})
            if event == 'charge.success':
                reference = data.get('reference')
                metadata = data.get('metadata', {})
                email = metadata.get('email')
                plan_type = metadata.get('plan_type')
                signup_token = metadata.get('signup_token')
                business_owner_id = metadata.get('business_owner_id')
                is_renewal = metadata.get('is_renewal', False)
                amount = data.get('amount')
                transaction_type = 'renewal' if is_renewal else 'signup'
                user = None
                signup_token_obj = None
                # Idempotency check
                if PaymentTransaction.objects.filter(reference=reference, status='success').exists():
                    return Response({'status': 'already_processed', 'message': 'This payment reference has already been processed.'})
                if is_renewal and business_owner_id:
                    try:
                        user = BusinessOwner.objects.get(id=business_owner_id)
                        duration_days = 365 if plan_type == 'yearly' else 30
                        user.activate_subscription(duration_days=duration_days, plan_type=plan_type)
                        user.last_payment_reference = reference
                        user.last_payment_date = timezone.now()
                        user.save()
                        send_payment_confirmation_email(user)
                    except BusinessOwner.DoesNotExist:
                        return Response({'error': 'Business owner not found'}, status=status.HTTP_400_BAD_REQUEST)
                elif signup_token:
                    try:
                        signup_token_obj = SignupToken.objects.get(token=signup_token, email=email)
                        if signup_token_obj.is_used:
                            return Response({'error': 'Signup token already used'}, status=status.HTTP_400_BAD_REQUEST)
                        signup_token_obj.is_used = True
                        signup_token_obj.save()
                        duration_days = metadata.get('duration_days', 30)
                        send_signup_token_email(email, signup_token, duration_days)
                    except SignupToken.DoesNotExist:
                        return Response({'error': 'Signup token not found'}, status=status.HTTP_400_BAD_REQUEST)
                PaymentTransaction.objects.create(
                    reference=reference,
                    email=email,
                    user=user,
                    amount=amount,
                    status='success',
                    transaction_type=transaction_type,
                    metadata=metadata,
                    signup_token=signup_token_obj
                )
                return Response({'status': 'success', 'message': 'Webhook payment processed.'})
            else:
                # Record non-successful or other event
                PaymentTransaction.objects.create(
                    reference=data.get('reference', ''),
                    email=data.get('customer', {}).get('email', ''),
                    user=None,
                    amount=data.get('amount'),
                    status=event,
                    transaction_type='webhook',
                    metadata=data,
                    signup_token=None
                )
                return Response({'status': 'ignored', 'message': 'Event not charge.success'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)