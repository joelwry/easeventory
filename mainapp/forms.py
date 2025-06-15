from django import forms
from .models import InventoryItem, Category, Sale

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'parent', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'parent': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class InventoryItemForm(forms.ModelForm):
    class Meta:
        model = InventoryItem
        fields = ['name', 'size', 'price', 'quantity', 'owner', 'category']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'size': forms.TextInput(attrs={'class': 'form-control'}),
            'price': forms.NumberInput(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'owner': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
        }

class SaleForm(forms.ModelForm):
    class Meta:
        model = Sale
        fields = ['item', 'quantity_sold', 'total_price', 'customer']
        widgets = {
            'item': forms.Select(attrs={'class': 'form-select'}),
            'quantity_sold': forms.NumberInput(attrs={'class': 'form-control'}),
            'total_price': forms.NumberInput(attrs={'class': 'form-control'}),
            'customer': forms.Select(attrs={'class': 'form-select'}),
        }