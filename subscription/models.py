from django.db import models
from django.contrib import auth

from paypal.standard import ipn

import signals

class Transaction(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    subscription = models.ForeignKey('subscription.Subscription', null=True, blank=True)
    user = models.ForeignKey(auth.models.User, null=True, blank=True)
    ipn = models.ForeignKey(ipn.models.PayPalIPN, null=True, blank=True)
    event = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    comment = models.TextField(blank=True, default='')

    class Meta:
        ordering = ('-timestamp',)

class Subscription(models.Model):
    name = models.CharField(max_length=100, unique=True, null=False)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=4, decimal_places=2)
    recurrence_period = models.PositiveIntegerField(null=True, blank=True)
    recurrence_unit = models.CharField(max_length=1, null=True,
                                       choices = ((None, "No recurrence"),
                                                  ('D', 'Day'),
                                                  ('W', 'Week'),
                                                  ('M', 'Month'),
                                                  ('Y', 'Year')))
    group = models.OneToOneField(auth.models.Group)

    class Meta:
        ordering = ('price','-recurrence_period')

    def __unicode__(self): return self.name

    @models.permalink
    def get_absolute_url(self):
        return ( 'subscription_detail', (), dict(object_id=str(self.id)) )

    def get_pricing_display(self):
        if not self.price: return u'Free'
        elif self.recurrence_period:
            if self.recurrence_period == 1:
                return '%.02f / %s' % (self.price,
                                       self.get_recurrence_unit_display())
            else:
                return '%.02f / %s %s' % (self.price,
                                          self.recurrence_period,
                                          self.get_recurrence_unit_display())
        else: return '%.02f one-time fee' % self.price

# add User.get_subscription() method
def __user_get_subscription(user):
    if not hasattr(user, '_subscription_cache'):
        sl = Subscription.objects.filter(group__in=user.groups.all())[:1]
        if sl: user._subscription_cache = sl[0]
        else: user._subscription_cache = None
    return user._subscription_cache
auth.models.User.add_to_class('get_subscription', __user_get_subscription)


#### Handle PayPal signals

def _payment_args(payment):
    try: s = Subscription.objects.get(id=payment.item_number)
    except Subscription.DoesNotExist: s = None

    try: u = auth.models.User.objects.get(id=payment.custom)
    except auth.models.User.DoesNotExist: u = None
    
    return (s,u)

def handle_payment_was_successful(sender, **kwargs):
    s, u = _payment_args(sender)
    if s and u:
        if not s.recurrence_unit:
            u.groups.add(s.group)
            u.save()
            Transaction(user=u, subscription=s, ipn=sender,
                        event='one-time payment', amount=sender.mc_gross
                        ).save()
            signals.signed_up.send(s, ipn=sender, subscription=s, user=u)
        else:
            Transaction(user=u, subscription=s, ipn=sender,
                        event='subscription payment', amount=sender.mc_gross
                        ).save()
            signals.paid.send(s, ipn=sender, subscription=s, user=u)
    else:
        Transaction(user=u, subscription=s, ipn=sender,
                    event='unexpected payment', amount=sender.mc_gross
                    ).save()
        signals.event.send(s, ipn=sender, subscription=s, user=u, event='unexpected_payment')
ipn.signals.payment_was_successful.connect(handle_payment_was_successful)

def handle_payment_was_flagged(sender, **kwargs):
    s, u = _payment_args(sender)
    Transaction(user=u, subscription=s, ipn=sender,
                event='payment flagged', amount=sender.mc_gross
                ).save()
    signals.event.send(s, ipn=sender, subscription=s, user=u, event='flagged')
ipn.signals.payment_was_flagged.connect(handle_payment_was_flagged)

def handle_subscription_signup(sender, **kwargs):
    s, u = _payment_args(sender)
    if u and s:
        u.groups.add(s.group)
        u.save()
        Transaction(user=u, subscription=s, ipn=sender,
                    event='subscribed', amount=sender.mc_gross
                    ).save()
        signals.subscribed.send(s, ipn=sender, subscription=s, user=u)
    else:
        Transaction(user=u, subscription=s, ipn=sender,
                    event='unexpected subscription', amount=sender.mc_gross
                    ).save()
        signals.event.send(s, ipn=sender, subscription=s, user=u, event='unexpected_subscription')
ipn.signals.subscription_signup.connect(handle_subscription_signup)

## FIXME: sanity checks on unsubscribe (is user really subscribe? What if not?)
def handle_subscription_cancel(sender, **kwargs):
    s, u = _payment_args(sender)
    if u and s:
        u.groups.remove(s.group)
        u.save()
        Transaction(user=u, subscription=s, ipn=sender,
                    event='cancel subscription', amount=sender.mc_gross
                    ).save()
        signals.unsubscribed.send(s, ipn=sender, subscription=s, user=u,
                                  reason='cancel')
    else:
        Transaction(user=u, subscription=s, ipn=sender,
                    event='unexpected cancel', amount=sender.mc_gross
                    ).save()
        signals.event.send(s, ipn=sender, subscription=s, user=u, event='unexpected_cancel')
ipn.signals.subscription_cancel.connect(handle_subscription_cancel)

def handle_subscription_eot(sender, **kwargs):
    s, u = _payment_args(sender)
    if u and s:
        u.groups.remove(s.group)
        u.save()
        Transaction(user=u, subscription=s, ipn=sender,
                    event='expired subscription', amount=sender.mc_gross
                    ).save()
        signals.unsubscribed.send(s, ipn=sender, subscription=s, user=u,
                                  reason='eot')
    else:
        Transaction(user=u, subscription=s, ipn=sender,
                    event='unexpected expiration', amount=sender.mc_gross
                    ).save()
        signals.event.send(s, ipn=sender, subscription=s, user=u, event='unexpected_expiration')
ipn.signals.subscription_eot.connect(handle_subscription_eot)

def handle_subscription_modify(sender, **kwargs):
    s, u = _payment_args(sender)
    Transaction(user=u, subscription=s, ipn=sender,
                event='modify subscription', amount=sender.mc_gross
                ).save()
    signals.event.send(s, ipn=sender, subscription=s, user=u, event='subscription_modify')
ipn.signals.subscription_modify.connect(handle_subscription_modify)
