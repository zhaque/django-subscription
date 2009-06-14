from django import forms
from django.contrib import admin
from django.utils.html import conditional_escape as esc

from models import Subscription, UserSubscription, Transaction

def _pricing(sub): return sub.get_pricing_display()

class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('name', _pricing)
admin.site.register(Subscription, SubscriptionAdmin)

def _subscription(trans):
    return u'<a href="/admin/subscription/subscription/%d/">%s</a>' % (
        trans.subscription.pk, esc(trans.subscription) )
_subscription.allow_tags = True

def _user(trans):
    return u'<a href="/admin/auth/user/%d/">%s</a>' % (
        trans.user.pk, esc(trans.user) )
_user.allow_tags = True

def _ipn(trans):
    return u'<a href="/admin/ipn/paypalipn/%d/">#%s</a>' % (
        trans.ipn.pk, trans.ipn.pk )
_ipn.allow_tags = True

class UserSubscriptionAdminForm(forms.ModelForm):
    class Meta:
        model = UserSubscription
    fix_group_membership = forms.fields.BooleanField(required=False)
    extend_subscription = forms.fields.BooleanField(required=False)

class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ( '__unicode__', _user, _subscription, 'expires', 'valid' )
    list_display_links = ( '__unicode__', )
    list_filter = ('subscription', )
    date_hierarchy = 'expires'
    form = UserSubscriptionAdminForm
    fieldsets = (
        (None, {'fields' : ('user', 'subscription', 'expires', 'ipn')}),
        ('Actions', {'fields' : ('fix_group_membership', 'extend_subscription'),
                     'classes' : ('collapse',)}),
        )

    def save_model(self, request, obj, form, change):
        if form.cleaned_data['extend_subscription']:
            obj.extend()
        if form.cleaned_data['fix_group_membership']:
            obj.fix()
        obj.save()

    # action for Django-SVN or django-batch-admin app
    actions = ( 'fix', 'extend', )

    def fix(self, request, queryset):
        for us in queryset.all():
            us.fix()
    fix.short_description = 'Fix group membership'

    def extend(self, request, queryset):
        for us in queryset.all(): us.extend()
    extend.short_description = 'Extend subscription'

admin.site.register(UserSubscription, UserSubscriptionAdmin)

class TransactionAdmin(admin.ModelAdmin):
    date_hierarchy = 'timestamp'
    list_display = ('timestamp', 'id', 'event', _subscription, _user, _ipn, 'amount', 'comment')
    list_display_links = ('timestamp', 'id')
    list_filter = ('subscription', 'user')
admin.site.register(Transaction, TransactionAdmin)
