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
    path('logout/', LogoutView.as_view(next_page='login'), name='logout'),
    path('signup/<str:token>/', views.signup, name='signup'),
    path('login/', views.login, name='login'),
    path('customers/', views.customer_list, name='customer_list'),
    path('categories/', views.category_list, name='category_list'),
    path('payment/success/<str:paymentId>', views.payment_success_page, name='unauth_payment_success'),
    path('payment/verify/unauth', views.unathenticated_payment_verify_page, name='unathenticated_payment_verify'),
    path('subscription/renewal/success/', views.renewal_subscription_success_page, name='renewal_subscription_success'),

    path('', views.landing, name='landing'),
]
