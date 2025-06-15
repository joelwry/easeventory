from django.urls import path
from . import views
from django.contrib.auth.views import LogoutView

urlpatterns = [ 
    path('dashboard/', views.dashboard, name='dashboard'),
    path('inventory/', views.inventory_view, name='inventory'),
    path('sales/', views.sales, name='sales'),
    path('reports/', views.reports, name='reports'),
    path('subscription/', views.subscription, name='subscription'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('landing/', views.landing, name='landing'),
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
]