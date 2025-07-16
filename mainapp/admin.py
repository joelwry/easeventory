from django.contrib import admin, messages
from django.utils.html import format_html
from django.urls import path
from django.shortcuts import redirect, render
from django.utils import timezone
from .models import BusinessOwner, Category, Customer, InventoryItem, Sale, SaleItem, SignupToken, PaymentTransaction
from .utils import send_signup_token_email

# Custom admin for BusinessOwner
@admin.register(BusinessOwner)
class BusinessOwnerAdmin(admin.ModelAdmin):
    list_display = ("business_name", "email", "subscription_status", "subscription_start_date", "subscription_end_date", "is_subscription_active")
    readonly_fields = ("email", "username", "business_name", "phone_number", "address", "created_at", "updated_at", "subscription_token", "subscription_start_date", "subscription_end_date")
    actions = ["activate_subscription", "expire_subscription"]
    change_form_template = "admin/mainapp/businessowner/change_form.html"
    # The activate_subscription view uses the template: admin/mainapp/businessowner/activate_subscription.html

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<str:object_id>/activate-subscription/',
                self.admin_site.admin_view(self.process_activate_subscription),
                name='mainapp_businessowner_activate_subscription',
            ),
        ]
        return custom_urls + urls

    def activate_subscription(self, request, queryset):
        # Only allow one at a time for safety
        if queryset.count() != 1:
            self.message_user(request, "Please select exactly one business owner to activate/renew.", level=messages.ERROR)
            return
        owner = queryset.first()
        return redirect(f"../{owner.pk}/activate-subscription/")
    activate_subscription.short_description = "Activate/Renew Subscription"

    def expire_subscription(self, request, queryset):
        updated = queryset.update(subscription_status='expired', subscription_end_date=timezone.now())
        self.message_user(request, f"{updated} business owner(s) marked as expired.")
    expire_subscription.short_description = "Expire Subscription (Block Access)"

    def process_activate_subscription(self, request, object_id):
        owner = self.get_object(request, object_id)
        if not owner:
            self.message_user(request, "Business owner not found.", level=messages.ERROR)
            return redirect("../../")
        if request.method == "POST":
            duration = int(request.POST.get("duration", 30))
            owner.activate_subscription(duration_days=duration)
            owner.generate_subscription_token()
            self.message_user(request, f"Subscription activated/renewed for {duration} days.")
            return redirect(f"../../{object_id}/change/")
        return render(request, "admin/mainapp/businessowner/activate_subscription.html", {
            "opts": self.model._meta,
            "owner": owner,
        })

    def has_add_permission(self, request):
        # Prevent admin from adding business owners directly
        return False

    def has_delete_permission(self, request, obj=None):
        # Prevent admin from deleting business owners
        return False

    def get_readonly_fields(self, request, obj=None):
        # Make all fields readonly except subscription management
        ro = list(self.readonly_fields)
        if obj:
            ro += [f.name for f in self.model._meta.fields if f.name not in [
                "subscription_status", "subscription_token", "subscription_start_date", "subscription_end_date"
            ]]
        return list(set(ro))

    def get_fieldsets(self, request, obj=None):
        # Group fields for clarity
        return [
            (None, {"fields": ("business_name", "email", "subscription_status", "subscription_start_date", "subscription_end_date", "subscription_token")}),
            ("Contact Info", {"fields": ("phone_number", "address")}),
            ("Timestamps", {"fields": ("created_at", "updated_at")}),
        ]

    def get_inline_instances(self, request, obj=None):
        # Prevent editing related objects from BusinessOwner admin
        return []

# Custom admin for SignupToken
@admin.register(SignupToken)
class SignupTokenAdmin(admin.ModelAdmin):
    list_display = ("email", "token", "expires_at", "is_used", "duration_days", "signup_url")
    readonly_fields = ("token", "expires_at", "is_used", "created_at")
    actions = ["generate_signup_token"]
    fields = ("email", "duration_days", "token", "expires_at", "is_used", "created_at")

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        # Set choices for duration_days
        form.base_fields["duration_days"].widget.choices = [
            (30, "1 Month (30 days)"),
            (180, "6 Months (180 days)"),
            (365, "1 Year (365 days)"),
            (730, "2 Years (730 days)")
        ]
        form.base_fields["duration_days"].required = False
        return form

    def save_model(self, request, obj, form, change):
        """Override save to send email when creating new token"""
        is_new = obj.pk is None
        super().save_model(request, obj, form, change)
        
        # Send email for new tokens with duration
        if is_new and obj.duration_days:
            if send_signup_token_email(obj.email, obj.token, obj.duration_days):
                self.message_user(request, f"Signup token created and email sent to {obj.email}")
            else:
                self.message_user(request, f"Signup token created but failed to send email to {obj.email}", level=messages.WARNING)

    def signup_url(self, obj):
        # Use get_absolute_url if available, else fallback
        if not obj.token:
            return "-"
        # This will be replaced in changelist_view with the full URL
        return format_html('<span class="signup-url" data-token="{}">(Click to copy)</span>', obj.token)
    signup_url.short_description = "Signup URL"

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context)
        # Inject JS for copy button and replace signup-url spans with full URLs
        if hasattr(response, 'render'):
            response.render()
            base_url = request.build_absolute_uri('/')[:-1]  # Remove trailing slash
            import re
            content = response.content.decode()
            def repl(m):
                token = m.group(1)
                full_url = f"{base_url}/signup/{token}/"
                return f'<button class="copy-signup-url" data-url="{full_url}">Copy Signup URL</button> <code>{full_url}</code>'
            content = re.sub(r'<span class="signup-url" data-token="([^"]+)">\(Click to copy\)</span>', repl, content)
            # Add JS for copy
            js = '''<script>
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('.copy-signup-url').forEach(function(btn) {
    btn.addEventListener('click', function() {
      navigator.clipboard.writeText(btn.getAttribute('data-url'));
      btn.textContent = 'Copied!';
      setTimeout(function(){ btn.textContent = 'Copy Signup URL'; }, 1500);
    });
  });
});
</script>'''
            if '</body>' in content:
                content = content.replace('</body>', js + '</body>')
            response.content = content.encode()
        return response

    def generate_signup_token(self, request, queryset):
        for obj in queryset:
            if not obj.is_used and obj.is_valid:
                self.message_user(request, f"Token for {obj.email} is already valid.")
                continue
            
            # Delete existing token and create new one
            SignupToken.objects.filter(email=obj.email).delete()
            new_token = SignupToken.generate_token(obj.email)
            
            # Set duration if it was set on the original object
            if obj.duration_days:
                new_token.duration_days = obj.duration_days
                new_token.save()
                
                # Send email with new token
                if send_signup_token_email(new_token.email, new_token.token, new_token.duration_days):
                    self.message_user(request, f"New token generated and email sent to {new_token.email}")
                else:
                    self.message_user(request, f"New token generated but failed to send email to {new_token.email}", level=messages.WARNING)
            else:
                self.message_user(request, f"New token generated for {new_token.email}")
    generate_signup_token.short_description = "Generate new signup token for selected emails"

    def has_add_permission(self, request):
        return True

    def has_delete_permission(self, request, obj=None):
        return True

class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def has_delete_permission(self, request, obj=None):
        return False
    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

admin.site.unregister(Category) if admin.site.is_registered(Category) else None
admin.site.unregister(Customer) if admin.site.is_registered(Customer) else None
admin.site.unregister(InventoryItem) if admin.site.is_registered(InventoryItem) else None
admin.site.unregister(Sale) if admin.site.is_registered(Sale) else None
admin.site.unregister(SaleItem) if admin.site.is_registered(SaleItem) else None
admin.site.unregister(PaymentTransaction) if admin.site.is_registered(PaymentTransaction) else None

admin.site.register(Category, ReadOnlyAdmin)
admin.site.register(Customer, ReadOnlyAdmin)
admin.site.register(InventoryItem, ReadOnlyAdmin)
admin.site.register(Sale, ReadOnlyAdmin)
admin.site.register(SaleItem, ReadOnlyAdmin)
admin.site.register(PaymentTransaction)
