from rest_framework import serializers
from mainapp.models import Customer, Category, InventoryItem, Notification, Sale, BusinessOwner, SaleItem

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessOwner
        fields = ('id', 'email', 'username', 'business_name', 'phone_number')
        read_only_fields = ('id',)

class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ['id', 'first_name', 'last_name', 'email', 'phone', 'created_at']
        read_only_fields = ['id', 'created_at']

class CategorySerial(serializers.ModelSerializer):
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'created_at', 'item_count']
        read_only_fields = ['id', 'created_at', 'item_count']

    def get_item_count(self, obj):
        return obj.items.count()

class CategorySerializer(serializers.ModelSerializer):
    """
    Serializer for the Category model.

    Includes a read-only field 'item_count' to represent the number of
    inventory items associated with the category.
    """
    # This field calculates the item count based on the annotation we'll add in the view.
    item_count = serializers.IntegerField(read_only=True)
    # Formatting the created_at field for better display on the frontend.
    created_at_formatted = serializers.DateTimeField(source='created_at', format="%b %d, %Y", read_only=True)

    class Meta:
        model = Category
        # Fields to be included in the serialized output.
        fields = ['id', 'name', 'created_at', 'created_at_formatted', 'item_count']

    
class InventoryItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    
    class Meta:
        model = InventoryItem
        fields = ['id', 'name', 'sku', 'category', 'category_name', 'size', 'price', 
                 'quantity', 'min_stock', 'status', 'created_at', 'updated_at', 'business_owner']
        read_only_fields = ['id', 'sku', 'status', 'created_at', 'updated_at']
        extra_kwargs = {
            'business_owner': {'write_only': True}
        }

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Name cannot be empty or just spaces.")
        return value

    def validate_quantity(self, value):
        if value < 0:
            raise serializers.ValidationError("Quantity must be zero or greater.")
        return value

    def validate_price(self, value):
        if value < 0:
            raise serializers.ValidationError("Price must be zero or greater.")
        return value

class SaleItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    class Meta:
        model = SaleItem
        fields = ['id', 'item', 'item_name', 'quantity', 'price_at_sale']
        read_only_fields = ['id', 'item_name']

class SaleSerializer(serializers.ModelSerializer):
    customer_name = serializers.SerializerMethodField()
    items = SaleItemSerializer(source='saleitem_set', many=True, read_only=True)
    business_name = serializers.CharField(source='business_owner.business_name', read_only=True)
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M", read_only=True)
    class Meta:
        model = Sale
        fields = ['id', 'customer', 'customer_name', 'total_amount', 'created_at', 'items', 'business_name']
        read_only_fields = ['id', 'created_at', 'items', 'business_name']

    def get_customer_name(self, obj):
        return f"{obj.customer.first_name} {obj.customer.last_name}"


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "title", "message", "created_at"]
        