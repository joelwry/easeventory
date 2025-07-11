from django.urls import path
from . import views
from django.contrib.auth.views import LogoutView

urlpatterns = [ 
    path('dashboard/', views.dashboard, name='dashboard'),
    path('inventory/', views.inventory_view, name='inventory'),
    path('inventory/category/<int:category_id>/', views.inventory_category_view, name='inventory_category'),
    path('sales/', views.sales, name='sales'),
    path('reports/', views.reports, name='reports'),
    path('subscription/', views.subscription, name='subscription'),
    path('payment/success/', views.payment_success, name='payment_success'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('signup/<str:token>/', views.signup, name='signup'),
    path('login/', views.login, name='login'),
    path('customers/', views.customer_list, name='customer_list'),
    path('customers/add/', views.add_customer, name='add_customer'),
    path('customers/<int:customer_id>/edit/', views.edit_customer, name='edit_customer'),
    path('customers/<int:customer_id>/delete/', views.delete_customer, name='delete_customer'),
    path('categories/', views.category_list, name='category_list'),
    path('categories/add/', views.add_category, name='add_category'),
    path('categories/<int:category_id>/edit/', views.edit_category, name='edit_category'),
    path('categories/<int:category_id>/delete/', views.delete_category, name='delete_category'),
    path('subscription-expired/', views.subscription_expired, name='subscription_expired'),
    path('', views.landing, name='landing'),
]
