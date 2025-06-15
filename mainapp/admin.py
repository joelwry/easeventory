from django.contrib import admin
from .models import BusinessOwner,Category,Customer,InventoryItem,Sale,SaleItem,SignupToken 


admin.site.register([BusinessOwner,Category,Customer,InventoryItem,Sale,SaleItem,SignupToken])

# Register your models here.
