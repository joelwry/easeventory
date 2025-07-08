from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token
from .views import (
    paystack_callback,
    inventory_list_api, customer_list_api, customer_detail_api,
    category_list_count,
    add_inventory_item, update_inventory_item, delete_inventory_item, adjust_stock, inventory_stats,
    analytics_data, export_sales_csv, export_inventory_csv
)
from . import views
from django.contrib.auth.views import LogoutView

router = DefaultRouter()

#router.register(r'customers', views.CustomerViewSet, basename='customer')
router.register(r'categories', views.CategoryViewSet, basename='category')
router.register(r'sales', views.SaleViewSet, basename='sale')

urlpatterns = [
    path('logout/', LogoutView.as_view(), name='logout'),
    path('paystack/callback/', paystack_callback, name='paystack_callback'),
    path('', include(router.urls)),
    path('inventory/list/', inventory_list_api, name='inventory-list'),
    path('inventory/add/', add_inventory_item, name='inventory-add'),
    path('inventory/<int:item_id>/update/', update_inventory_item, name='inventory-update'),
    path('inventory/<int:item_id>/delete/', delete_inventory_item, name='inventory-delete'),
    path('inventory/<int:item_id>/adjust-stock/', adjust_stock, name='inventory-adjust-stock'),
    path('inventory/stats/', inventory_stats, name='inventory-stats'),
    path('inventory/category/<int:category_id>/list/', views.category_inventory_list_api, name='category-inventory-list'),
    path('customers/list/', customer_list_api, name='customer-list'),
    path('customers/<int:customer_id>/', customer_detail_api, name='customer-detail'),
    path('category/list-count/', category_list_count, name='category-list-count'),
    #path('categories/list/', category_list_api, name='category-list'),
    #path('categories/<int:category_id>/', category_detail_api, name='category-detail'),
    path('auth/signup/', views.signup_api, name='signup-api'),
    path('auth/login/', views.login_api, name='login-api'),
    path('api-token-auth/', obtain_auth_token, name='api_token_auth'),
    path('analytics/', analytics_data, name='analytics-data'),
    path('export/sales/', export_sales_csv, name='export-sales-csv'),
    path('export/inventory/', export_inventory_csv, name='export-inventory-csv'),
]
