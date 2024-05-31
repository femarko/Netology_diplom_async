from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from backend.models import User, Shop, Category, Product, ProductInfo, Parameter, ProductParameter, Order, OrderItem, \
    Contact, ConfirmEmailToken


class CustomUserInline(admin.TabularInline):
    model = User
    extra = 0


class ContactInline(admin.TabularInline):
    model = Contact
    extra = 0


class ShopInline(admin.TabularInline):
    model = Shop
    extra = 0

class ProductInfoInline(admin.TabularInline):
    model = ProductInfo
    extra = 0


class ProductInline(admin.TabularInline):
    model = Product
    extra = 0


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


class OrderInline(admin.TabularInline):
    model = Order
    extra = 0


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    """
    Панель управления пользователями
    """
    model = User

    fieldsets = (
        (None, {'fields': ('email', 'password', 'type')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'company', 'position')}),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    list_display = ("id", 'email', 'first_name', 'last_name', 'is_staff', 'is_active', 'last_login', 'date_joined',
                    'type')
    list_filter = ("type",)
    inlines = (ContactInline, ShopInline)


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ("name", "url", "user", "state")
    list_filter = ("state",)
    inlines = (ProductInfoInline,)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name",)
    inlines = (ProductInfoInline,)


@admin.register(ProductInfo)
class ProductInfoAdmin(admin.ModelAdmin):
    list_display = ("id", "model", "external_id", "product", "shop", "quantity", "price", "price_rrc")
    inlines = (OrderItemInline,)


@admin.register(Parameter)
class ParameterAdmin(admin.ModelAdmin):
    list_display = ("name",)


@admin.register(ProductParameter)
class ProductParameterAdmin(admin.ModelAdmin):
    list_display = ("product_info", "parameter", "value")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("user", "dt", "state", "contact")
    inlines = (OrderItemInline,)


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "product_info", "quantity")
    # inlines = (ProductInfoInline,)


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "city", "street", "house", "structure", "building", "apartment", "phone")


@admin.register(ConfirmEmailToken)
class ConfirmEmailTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'key', 'created_at',)
