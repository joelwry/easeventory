from django.shortcuts import get_object_or_404

from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAuthenticated, AllowAny
from rest_framework.decorators import api_view, permission_classes, authentication_classes, action
from rest_framework.authentication import TokenAuthentication
from django.views.decorators.csrf import csrf_exempt
from .serializers import InventoryItemSerializer, SaleSerializer, CustomerSerializer, CategorySerializer, UserSerializer
from django.http import HttpResponseBadRequest, JsonResponse
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate,login
from django.contrib.auth.models import User
from mainapp.models import Customer, SignupToken, BusinessOwner
from mainapp.models import InventoryItem,Sale
from django.db.models import F, Sum
from mainapp.models import Category

import logging

logger = logging.getLogger(__name__)

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
def delete_inventory_item(request, item_id):
    """API endpoint for deleting an inventory item"""
    business_owner = request.user
    item = get_object_or_404(InventoryItem, id=item_id, business_owner=business_owner)
    
    item.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
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

@api_view(['GET', 'POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
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

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
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
        # Create business owner directly
        business_owner = BusinessOwner.objects.create_user(
            username=email,  # Use email as username
            email=email,
            password=password,
            business_name=business_name,
            telephone=phone_number,
            address=address
        )
        
        # Mark token as used
        signup_token = SignupToken.objects.get(token=token)
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
                'address': business_owner.address
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
