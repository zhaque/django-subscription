import datetime

from django.conf import settings
from django.db import models
from django.contrib import auth

from paypal.standard import ipn

import signals, utils

class Transaction(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True, editable=False)
    subscription = models.ForeignKey('subscription.Subscription',
                                     null=True, blank=True, editable=False)
    user = models.ForeignKey(auth.models.User,
                             null=True, blank=True, editable=False)
    ipn = models.ForeignKey(ipn.models.PayPalIPN,
                            null=True, blank=True, editable=False)
    event = models.CharField(max_length=100, editable=False)
    amount = models.DecimalField(max_digits=64, decimal_places=2,
                                 null=True, blank=True, editable=False)
    comment = models.TextField(blank=True, default='')

    class Meta:
        ordering = ('-timestamp',)

class Subscription(models.Model):
    name = models.CharField(max_length=100, unique=True, null=False)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=64, decimal_places=2)
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

class UserSubscription(models.Model):
    user = models.OneToOneField(auth.models.User, primary_key=True)
    subscription = models.ForeignKey(Subscription)
    expires = models.DateField(null = True)
    ipn = models.ForeignKey(ipn.models.PayPalIPN, default=None,
                            null=True, blank=True)

    grace_timedelta = datetime.timedelta(
        getattr(settings, 'SUBSCRIPTION_GRACE_PERIOD', 2))

    def user_is_group_member(self):
        "Returns True is user is member of subscription's group"
        return self.subscription.group in self.user.groups.all()
    user_is_group_member.boolean = True

    def expired(self):
        """Returns true if there is more than SUBSCRIPTION_GRACE_PERIOD
        days after expiration date."""
        return self.expires is not None and (
            self.expires + self.grace_timedelta < datetime.date.today() )
    expired.boolean = True

    def valid(self):
        """Validate group membership.

        Returns True if not expired and user is in group, or expired
        and user is not in group."""
        if self.expired(): return not self.user_is_group_member()
        else: return self.user_is_group_member()
    valid.boolean = True

    def unsubscribe(self):
        """Unsubscribe user."""
        self.user.groups.remove(self.subscription.group)
        self.user.save()

    def subscribe(self):
        """Subscribe user."""
        self.user.groups.add(self.subscription.group)
        self.user.save()

    def fix(self):
        """Fix group membership if not valid()."""
        if not self.valid():
            if self.expired(): self.unsubscribe()
            else: self.subscribe()

    def extend(self, timedelta=None):
        """Extend subscription by `timedelta' or by subscription's
        recurrence period."""
        if timedelta is not None:
            self.expires += timedelta
        else:
            if self.subscription.recurrence_unit:
                self.expires = utils.extend_date_by(
                    self.expires,
                    self.subscription.recurrence_period,
                    self.subscription.recurrence_unit)
            else:
                self.expires = None

    def try_change(self, subscription):
        """Check whether upgrading/downgrading to `subscription' is possible.

        If subscription change is possible, returns false value; if
        change is impossible, returns a list of reasons to display.

        Checks are performed by sending
        subscription.signals.change_check with sender being
        UserSubscription object, and additional parameter
        `subscription' being new Subscription instance.  Signal
        listeners should return None if change is possible, or a
        reason to display.
        """
        if self.subscription == subscription:
            return [ u'This is your current subscription.' ]
        return [
            res[1]
            for res in signals.change_check.send(
                self, subscription=subscription)
            if res[1] ]

    def __unicode__(self):
        rv = u"%s's %s" % ( self.user, self.subscription )
        if self.expired():
            rv += u' (expired)'
        return rv

def unsubscribe_expired():
    """Unsubscribes all users whose subscription has expired.

    Loops through all UserSubscription objects with `expires' field
    earlier than datetime.date.today() - SUBSCRIPTION_GRACE_PERIOD,
    and unsubscribes user."""
    for u in User.objects.get(
          expires__lt=datetime.date.today() - UserSubscription.grace_timedelta):
        u.usersubscription.unsubscribe()

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
            try:
                us = u.usersubscription
            except UserSubscription.DoesNotExist:
                us = UserSubscription(
                    user = u,
                    subscription = s,
                    expires = None,
                    ipn = sender)
            else:
                us.subscription = s     # FIXME: upgrade/downgrade
                us.expires = None
                us.ipn = sender
            # FIXME: check price
            us.subscribe()
            us.save()
            Transaction(user=u, subscription=s, ipn=sender,
                        event='one-time payment', amount=sender.mc_gross
                        ).save()
            signals.signed_up.send(s, ipn=sender, subscription=s, user=u)
        else:
            try: us = u.usersubscription
            except UserSubscription.DoesNotExist:
                Transaction(user=u, subscription=s, ipn=sender,
                            event='unexpected payment',
                            amount=sender.mc_gross,
                            comment='Subscription payment for user with no active subscription.',
                            ).save()
                signals.event.send(s, ipn=sender, subscription=s, user=u, event='unexpected_payment')
            # FIXME: check price
            us.extend()
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
        try:
            us = u.usersubscription
        except UserSubscription.DoesNotExist:
            us = UserSubscription(
                user = u,
                subscription = s,
                expires = datetime.date.today(),
                ipn = sender)
        else:
            us.subscription = s     # FIXME: upgrade/downgrade
            us.expires = datetime.date.today()
            us.ipn = sender
        # FIXME: check price
        us.subscribe()
        us.save()
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

## FIXME: sanity checks on unsubscribe (is user really subscribed? What if not?)
def handle_subscription_cancel(sender, **kwargs):
    s, u = _payment_args(sender)
    if u and s:
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
