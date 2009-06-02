from django.contrib import admin
from django.utils.html import conditional_escape as esc

from models import Subscription, Transaction

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

class TransactionAdmin(admin.ModelAdmin):
    date_hierarchy = 'timestamp'
    list_display = ('timestamp', 'id', 'event', _subscription, _user, _ipn, 'amount', 'comment')
    list_display_links = ('timestamp', 'id')
admin.site.register(Transaction, TransactionAdmin)
