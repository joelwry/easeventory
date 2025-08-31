from django.shortcuts import get_object_or_404

from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAuthenticated, AllowAny
from rest_framework.decorators import api_view, permission_classes, authentication_classes, action
from rest_framework.authentication import TokenAuthentication
from django.views.decorators.csrf import csrf_exempt
from .serializers import InventoryItemSerializer, NotificationSerializer, SaleSerializer, CustomerSerializer, CategorySerializer, UserSerializer
from django.http import HttpResponseBadRequest, JsonResponse, HttpResponse
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate,login
from django.contrib.auth.models import User
from mainapp.models import Customer, Notification, SaleItem, SignupToken, BusinessOwner
from mainapp.models import InventoryItem,Sale
from django.db.models import F, Sum
from mainapp.models import Category
from datetime import timedelta
from django.utils import timezone
import csv
from mainapp.utils import active_subscription_required, send_welcome_email, verify_paystack_webhook, send_signup_token_email, send_payment_confirmation_email
import requests
import json
from rest_framework import status
import logging
import os
from django.conf import settings
from mainapp.models import PaymentTransaction  # Add this import
from rest_framework.views import APIView  # For PaystackWebhook2
from django.db.models import Q

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
    signup_token = get_object_or_404(SignupToken, token=token)
    if not signup_token.is_valid or signup_token.email != email:
        return Response({'error': 'Invalid or expired token'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Check if user already exists
    if BusinessOwner.objects.filter(email=email).exists():
        return Response(
            {'error': 'User with this email already exists'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Find the successful payment transaction linked to this signup token
    transaction = PaymentTransaction.objects.filter(
        signup_token=signup_token,
        status='success'
    ).first()

    if not transaction:
        return Response({'error': 'Payment verification failed. Please complete payment.'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        # Create business owner directly
        business_owner = BusinessOwner.objects.create_user(
            username=email,  # Use email as username
            email=email,
            password=password,
            business_name=business_name,
            telephone=phone_number,
            address=address
        )
        
        # Activate subscription
        business_owner.activate_subscription(
            duration_days=signup_token.duration_days,
            plan_type=transaction.metadata.get('plan_type', 'yearly')
        )

        # **CRUCIAL STEP**: Copy codes from transaction to the new BusinessOwner
        business_owner.paystack_customer_code = transaction.paystack_customer_code
        business_owner.paystack_subscription_code = transaction.paystack_subscription_code
        business_owner.last_payment_reference = transaction.reference
        business_owner.last_payment_date = transaction.processed_at
        business_owner.save()

        # Mark token and transaction as processed
        signup_token.is_used = True
        signup_token.save()
        transaction.user = business_owner
        transaction.save()

        # Send welcome email and generate auth token
        # send_welcome_email(business_owner)
        token, created = Token.objects.get_or_create(user=business_owner)

        return Response({
            'token': token.key,
            'user': UserSerializer(business_owner).data
        }, status=status.HTTP_201_CREATED)

        
    except Exception as e:
        logger.error(f"Error during signup for {email}: {e}")
        return Response({'error': 'An error occurred during signup.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
    # we should have a way to send the next url query parameters alongside so that we can redirect appropriately based on the next 
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
        plan_type = data.get('plan_type', 'yearly')

        if not email:
            return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)

        duration_days = 365 if plan_type == 'yearly' else 30 if plan_type == 'monthly' else 1
        signup_token = SignupToken.generate_token(email)
        signup_token.duration_days = duration_days
        signup_token.save() # Save the token to get an ID

        amount = YEARLY_SUBSCRIPTION_AMOUNT if plan_type == 'yearly' else MONTHLY_SUBSCRIPTION_AMOUNT if plan_type == 'monthly' else 10000
        plan = PAYSTACK_PLANS.get(plan_type)
        
        paystack_data = {
            'email': email,
            'amount': amount,
            'plan': plan,
            'callback_url': f"{settings.SITE_URL}/payment/success/{signup_token.token}/", # Use a success page URL
            'metadata': {
                'email': email,
                'plan_type': plan_type,
                'signup_token': signup_token.token,
                'transaction_type': 'signup'
            }
        }

        headers = {
            'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}',
            'Content-Type': 'application/json'
        }
        response = requests.post('https://api.paystack.co/transaction/initialize', headers=headers, json=paystack_data)

        if response.status_code == 200:
            paystack_response = response.json()['data']
            paystack_data['metadata']['intial_reference'] = paystack_response['reference']

            # PaymentTransaction record to track this payment
            PaymentTransaction.objects.create(
                reference=paystack_response['reference'],
                email=email,
                amount=amount,
                status='pending',
                transaction_type='signup',
                signup_token=signup_token,
                metadata=paystack_data['metadata']
            )

            return Response({
                'authorization_url': paystack_response['authorization_url'],
                'reference': paystack_response['reference'],
                'signup_token': signup_token.token,
                "amount": amount, 
                "plan_code": plan
            })
        else:
            logger.error(f"Paystack initialization failed: {response.text}")
            return Response({'error': 'Failed to initialize payment'}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"Error in initialize_payment: {e}")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initialize_renewal_payment(request):
    """Initialize payment for subscription renewal..subscription renewal is for a business owner that his or her subscription has expired"""
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

@api_view(['GET','POST'])
@permission_classes([AllowAny])
@permission_classes([AllowAny])
def verify_payment(request):
    """
    Verifies a payment reference manually.
    This serves as a fallback to the webhook. It finds a pending transaction,
    verifies it with Paystack, and updates it with success status and subscription codes.
    """
    reference = request.data.get('reference')
    initial_reference = request.data.get("initial_reference")
    
    print(f'CALLING MANUAL PAYMENT VERIFICATION {reference} / {initial_reference}')

    if not reference:
        return Response({'error': 'Reference is required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        # Step 1: Find the pending transaction created during initialization.
        
        transaction = PaymentTransaction.objects.filter(
            Q(reference=reference) | Q(reference=initial_reference)
        ).first()

        if not transaction : 
            return Response({
                'error': 'Payment Transaction not found for reference'
            }, status=status.HTTP_404_NOT_FOUND)

        if transaction.status =='success':
            token = transaction.signup_token.token # highlighted coz signup_token object can be set 2 null n blank
            
            if transaction.reference == initial_reference :
                transaction.reference = reference 
                transaction.save()
            return Response({
                'status': 'already_processed',
                'message': 'This payment has already been verified.',
                'signup_token': token
            }, status=status.HTTP_200_OK)
        
        # Step 2: Now we can Verify the transaction with Paystack.
        headers = {'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}'}
        response = requests.get(f'https://api.paystack.co/transaction/verify/{reference}', headers=headers)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        response_json = response.json()
        verification_data = response_json['data']

        print('VERFICATION DATA FOR PAYMENT')
        print(verification_data)
        print('With this verification data we should be able to get auth and subscription code if truly returned during the verification')    
        # Step 3: Check if Paystack confirms the payment was successful.
        if verification_data['status'] == 'success':
            # Update the transaction record with success status and codes.
            transaction.status = 'success'
            transaction.paystack_customer_code = verification_data.get('customer', {}).get('customer_code')
            transaction.reference = reference  #update reference back to normal paystack payment reference ....
            # The subscription code is often in the authorization details for plan payments.
            # This is a robust way to find it.
            auth_details = verification_data.get('authorization', {})
            if auth_details.get('channel') == 'subscription' or verification_data.get('plan'):
                 # Heuristic: Find the subscription code if available. Often requires webhook, but we check here.
                 # Note: The most reliable way to get sub code is the webhook. This is a fallback.
                 # We will assume for now the webhook will handle it, but we mark the payment as successful.
                 pass # The webhook is the primary source for the subscription code.

            transaction.save()

            # Step 4: Send the signup email to the user.
            if transaction.signup_token:
                send_signup_token_email(
                    email=transaction.email,
                    token=transaction.signup_token.token,
                    duration_days=transaction.signup_token.duration_days
                )

            # Step 5: Return a success response with the token for redirection.
            return Response({
                'status': 'success',
                'message': 'Payment verified successfully. Your signup link has been sent to your email.',
                'signup_token': transaction.signup_token.token # this is showing bcox of null & blank True in model
            }, status=status.HTTP_200_OK)
        
        else:
            # If Paystack says the payment was not successful.
            transaction.status = verification_data['status'] # e.g., 'failed'
            transaction.save()
            return Response({'error': 'Payment was not successful.'}, status=status.HTTP_400_BAD_REQUEST)

    except PaymentTransaction.DoesNotExist:
        return Response({'error': 'Invalid payment reference.'}, status=status.HTTP_404_NOT_FOUND)
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Paystack verification API error: {e}")
        return Response({'error': 'Could not connect to payment provider.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    except Exception as e:
        logger.error(f"An unexpected error occurred in verify_payment: {e}")
        return Response({'error': 'An internal error occurred.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def verify_renewal_payment(request):
    """Verify renewal payment for an authenticated business owner and update subscription."""
    try:
        # Debug logging
        logger.info(f"verify_renewal_payment called by user: {request.user.email}")
        logger.info(f"Request data: {request.data}")
        
        reference = request.data.get('reference')
        if not reference:
            logger.error("No reference provided in request")
            return Response({'error': 'Reference is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Check if this reference has already been processed
        existing_transaction = PaymentTransaction.objects.filter(reference=reference).first()
        if existing_transaction and existing_transaction.status == 'success':
            logger.info(f"Reference {reference} already processed successfully")
            return Response({'status': 'already_processed', 'message': 'This payment reference has already been processed.'})

        # Verify with Paystack
        headers = {
            'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}',
            'Content-Type': 'application/json'
        }
        
        logger.info(f"Verifying payment with Paystack for reference: {reference}")
        response = requests.get(
            f'https://api.paystack.co/transaction/verify/{reference}',
            headers=headers
        )

        if response.status_code != 200:
            logger.error(f"Paystack verification failed with status {response.status_code}: {response.text}")
            return Response({'error': 'Failed to verify payment with Paystack'}, status=status.HTTP_400_BAD_REQUEST)
        
        verification_data = response.json()
        logger.info(f"Paystack verification response: {verification_data}")
        
        paystack_status = verification_data['data']['status']
        metadata = verification_data['data'].get('metadata', {})
        plan_type = metadata.get('plan_type')
        is_renewal = metadata.get('is_renewal', False)
        amount = verification_data['data'].get('amount')
        user = request.user
        transaction_type = 'renewal'

        logger.info(f"Payment status: {paystack_status}, is_renewal: {is_renewal}, plan_type: {plan_type}")

        # Create or update PaymentTransaction record
        transaction_data = {
            'email': user.email,
            'user': user,
            'amount': amount,
            'status': paystack_status,
            'transaction_type': transaction_type,
            'metadata': metadata,
            'signup_token': None
        }

        try:
            if existing_transaction:
                # Update existing transaction
                for key, value in transaction_data.items():
                    setattr(existing_transaction, key, value)
                existing_transaction.save()
                logger.info(f"Updated existing transaction for reference: {reference}")
            else:
                # Create new transaction
                PaymentTransaction.objects.create(
                    reference=reference,
                    **transaction_data
                )
                logger.info(f"Created new transaction for reference: {reference}")
        except Exception as e:
            logger.error(f"Error creating/updating PaymentTransaction: {str(e)}")
            return Response({'error': f'Database error: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        if paystack_status == 'success' and is_renewal:
            logger.info(f"Processing successful renewal for user: {user.email}")
            duration_days = 365 if plan_type == 'yearly' else 30
            user.activate_subscription(duration_days=duration_days, plan_type=plan_type)
            user.last_payment_reference = reference
            user.last_payment_date = timezone.now()
            user.save()
            send_payment_confirmation_email(user)
            
            # Update transaction status to success
            if existing_transaction:
                existing_transaction.status = 'success'
                existing_transaction.save()
            else:
                PaymentTransaction.objects.filter(reference=reference).update(status='success')
            
            logger.info(f"Successfully renewed subscription for user: {user.email}")
            # On success, return a redirect URL to the renewal success page
            return Response({'status': 'success', 'redirect_url': '/renewal-subscription-success/'})
        else:
            logger.warning(f"Payment verification failed - status: {paystack_status}, is_renewal: {is_renewal}")
            return Response({'status': 'failed', 'message': 'Payment verification failed.'})
            
    except Exception as e:
        logger.error(f"Error in verify_renewal_payment: {str(e)}")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

# cancel subscription
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel_subscription(request):
    """
    API endpoint to cancel the authenticated user's subscription via Paystack.
    This now includes a two-step process: fetch the subscription token, then disable.
    """
    user = request.user
    subscription_code = user.paystack_subscription_code

    if not subscription_code:
        return Response({'status': 'error', 'message': 'No active subscription code found for this user.'}, status=status.HTTP_400_BAD_REQUEST)

    headers = {
        'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}',
        'Content-Type': 'application/json',
    }

    try:
        # Step 1: Fetch the subscription from Paystack to get the email_token
        fetch_url = f'https://api.paystack.co/subscription/{subscription_code}'
        fetch_response = requests.get(fetch_url, headers=headers)
        fetch_response.raise_for_status() # Will raise an error for non-2xx responses
        
        subscription_data = fetch_response.json()['data']
        email_token = subscription_data.get('email_token')

        if not email_token:
            return Response({'status': 'error', 'message': 'Could not retrieve subscription token from Paystack.'}, status=status.HTTP_400_BAD_REQUEST)

        # Step 2: Use the subscription_code and email_token to disable the subscription
        disable_url = 'https://api.paystack.co/subscription/disable'
        payload = {
            'code': subscription_code,
            'token': email_token
        }
        
        disable_response = requests.post(disable_url, headers=headers, json=payload)
        disable_response.raise_for_status()
        
        result = disable_response.json()

        if result.get('status'):
            # On successful cancellation, update the user's status in our database
            user.subscription_status = 'cancelled'
            user.save()
            return Response({'status': 'success', 'message': 'Your subscription has been cancelled successfully.'})
        else:
            return Response({'status': 'error', 'message': result.get('message', 'Failed to cancel subscription.')}, status=status.HTTP_400_BAD_REQUEST)

    except requests.exceptions.RequestException as e:
        logger.error(f"Paystack API error during cancellation for user {user.email}: {e}")
        return Response({'status': 'error', 'message': 'A communication error occurred with the payment provider.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        logger.error(f"Error cancelling subscription for user {user.email}: {e}")
        return Response({'status': 'error', 'message': 'An unexpected error occurred.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class PaystackWebhookAPIView(APIView):
    """
    Handles incoming webhooks from Paystack.
    Updates PaymentTransaction and BusinessOwner models.
    """
    permission_classes = [AllowAny]

    @csrf_exempt
    def post(self, request, *args, **kwargs):
        # 1️⃣ Verify webhook signature
        if not verify_paystack_webhook(request):
            return Response({'status': 'error', 'message': 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)

        payload = request.data
        event = payload.get('event')
        data = payload.get('data', {})
        try:
            # --- Event: Payment Success ---
            if event == 'charge.success':
                reference = data.get('reference')
                email = data.get('customer', {}).get('email')
                customer_code = data.get('customer', {}).get('customer_code')

                # Find latest transaction for this email
                transaction = PaymentTransaction.objects.filter(
                    email=email
                ).order_by('-processed_at').first()
                
                if transaction and transaction.status == 'pending' and not transaction.user :
                    transaction.status = 'success'
                    transaction.paystack_customer_code = customer_code
                    transaction.reference = reference
                    transaction.metadata = {
                        **(transaction.metadata or {}),
                        "paystack_transaction_id": data.get('id'),
                        "plan_id": data.get('plan', {}).get('id'),
                        "plan_code": data.get('plan', {}).get('plan_code'),
                        "amount": data.get('amount'),
                        "paid_at": data.get('paid_at'),
                    }
                    transaction.save()

                    # Trigger email for signups... we doing this check since this event is called for both signup or renewal
                    if transaction.transaction_type == 'signup' and transaction.signup_token:
                        send_signup_token_email(
                            email=transaction.email,
                            token=transaction.signup_token.token,
                            duration_days=transaction.signup_token.duration_days
                        )
                        print(f"📧 Signup email sent to {transaction.email}")

                    # else if transacton.success can be in 2 ways now 
                    elif transaction and transaction.status == 'success':
                        # we might be referencing a renewal done on paystack end automatically hence we need to update the user subscription detail 
                        pass
                
                # WE assume this will be for renewal
                elif transaction and transaction.user is not None:
                    transaction.status = 'success'
                    transaction.reference = reference
                    transaction.paystack_customer_code = customer_code
                    transaction.metadata = {
                        **(transaction.metadata or {}),
                        "paystack_transaction_id": data.get('id'),
                        "plan_code": data.get('plan'),
                        "amount": data.get('amount')/100,
                        "paid_at": data.get('paid_at'),
                    }
                    transaction.save()

                    # Update BusinessOwner (renewal)
                    owner = transaction.user or BusinessOwner.objects.filter(email=email).first()
                    if owner:
                        owner.paystack_customer_code = customer_code
                        owner.last_payment_reference = reference
                        owner.last_payment_date = timezone.now()
                        owner.subscription_status = 'active'

                        # ✅ Handle renewal: extend subscription_end_date
                        if owner.subscription_end_date and timezone.now() < owner.subscription_end_date:
                            if owner.subscription_plan == "monthly":
                                owner.subscription_end_date += timezone.timedelta(days=30)
                            elif owner.subscription_plan == "yearly":
                                owner.subscription_end_date += timezone.timedelta(days=365)
                            # for testing we have hourly renewal
                            else :
                                owner.subscription_end_date += timezone.timedelta(hours=1)
                        owner.save()
                        print('RENEWAL SUCCESSFUL')

            # --- Event: Subscription Created ---
            elif event == 'subscription.create':
                customer_code = data.get('customer', {}).get('customer_code')
                subscription_code = data.get('subscription_code')
                email = data.get('customer', {}).get('email')
                
                transaction = PaymentTransaction.objects.filter(
                    email=email
                ).order_by('-processed_at').first()

                if transaction:
                    transaction.paystack_subscription_code = subscription_code
                    transaction.paystack_customer_code = customer_code
                    transaction.metadata = {
                        **(transaction.metadata or {}),
                        "subscription_status": data.get('status'),
                        "next_payment_date": data.get('next_payment_date'),
                    }
                    transaction.save()

                    # Attach to BusinessOwner
                    if transaction.user:
                        transaction.user.paystack_subscription_code = subscription_code
                        transaction.user.save()

            # --- Event: Invoice Create (reminder) ---
            elif event == 'invoice.create':
                # Could trigger reminder email
                pass

            # --- Event: Invoice Update (after charge attempt) ---
            elif event == 'invoice.update':
                status_val = data.get('status')
                subscription_code = data.get('subscription', {}).get('subscription_code')

                owner = BusinessOwner.objects.filter(paystack_subscription_code=subscription_code).first()
                if owner:
                    if status_val == "success":
                        owner.subscription_status = "active"
                        owner.save()
                    elif status_val == "failed":
                        owner.subscription_status = "expired"
                        owner.save()

            # --- Event: Payment Failed ---
            elif event == 'invoice.payment_failed':
                subscription_code = data.get('subscription_code')
                owner = BusinessOwner.objects.filter(paystack_subscription_code=subscription_code).first()
                if owner:
                    owner.subscription_status = 'expired'
                    owner.save()

            # --- Event: Subscription Cancelled (user turned off renew) ---
            elif event == 'subscription.not_renew':
                subscription_code = data.get('subscription_code')
                owner = BusinessOwner.objects.filter(paystack_subscription_code=subscription_code).first()
                if owner:
                    # Mark as cancelled, but keep active until end_date
                    owner.subscription_status = 'cancelled'
                    owner.save()

            # --- Event: Subscription Disabled (final disable) ---
            elif event == 'subscription.disable':
                subscription_code = data.get('subscription_code')
                owner = BusinessOwner.objects.filter(paystack_subscription_code=subscription_code).first()
                if owner:
                    owner.subscription_status = 'expired'
                    owner.save()

        except Exception as e:
            print(f"❌ Error processing webhook {event}: {e}")
            return Response({'status': 'error'}, status=status.HTTP_200_OK)

        return Response({'status': 'success'}, status=status.HTTP_200_OK)


# --- 2. NEW Polling Endpoint ---
@api_view(['GET'])
@permission_classes([AllowAny])
def check_payment_status(request):
    """
    Checks the status of a payment transaction from the database.
    Used by the frontend to poll for webhook confirmation.
    """
    reference = request.query_params.get('reference')
    initial_reference = request.query_params.get("initial_reference")
    print('Reference for querying with polling')
    print(f'Ref retrieved : {reference}')
    if not reference or initial_reference:
        return Response({'error': 'Reference is required'}, status=status.HTTP_400_BAD_REQUEST)

    try:

        reference = request.query_params.get("reference")
        initial_reference = request.query_params.get("initial_reference")

        transaction = PaymentTransaction.objects.filter(
            Q(reference=reference) | Q(initial_reference=initial_reference)
        ).first()

        if not transaction :
            return Response({'error': 'Payment record not found.'}, status=status.HTTP_404_NOT_FOUND) 
        
        if transaction.reference == initial_reference:
            transaction.reference = reference 

        if transaction.status == 'success':
            return Response({
                'status': transaction.status, # Will be 'pending', 'success', or 'failed'
                'signup_token': transaction.signup_token.token if transaction.signup_token else None
            })
        else:
            return Response({'status': status.HTTP_417_EXPECTATION_FAILED, 'message': 'Payment not completed yet.'})
    except PaymentTransaction.DoesNotExist:
        return Response({'error': 'Payment record not found.'}, status=status.HTTP_404_NOT_FOUND)
    
    except Exception as e :
        print(e)
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
# misc 
# List unread notifications for logged-in user
class UnreadNotificationsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notifications = Notification.objects.filter(owner=request.user, is_read=False)
        serializer = NotificationSerializer(notifications, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


# Delete (mark as read -> auto delete) a notification
class DeleteNotificationAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        try:
            notification = Notification.objects.get(pk=pk, owner=request.user)
            notification.mark_as_read()
            return Response({"message": "Notification deleted"}, status=status.HTTP_204_NO_CONTENT)
        except Notification.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)