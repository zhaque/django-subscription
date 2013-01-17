import datetime

from django.conf import settings
from django.db import models
from django.contrib import auth
from django.utils.translation import ugettext as _, ungettext, ugettext_lazy

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


_recurrence_unit_days = {
    'D' : 1.,
    'W' : 7.,
    'M' : 30.4368,                      # http://en.wikipedia.org/wiki/Month#Julian_and_Gregorian_calendars
    'Y' : 365.2425,                     # http://en.wikipedia.org/wiki/Year#Calendar_year
    }

_TIME_UNIT_CHOICES=(
    ('D', ugettext_lazy('Day')),
    ('W', ugettext_lazy('Week')),
    ('M', ugettext_lazy('Month')),
    ('Y', ugettext_lazy('Year')),
    )

class Subscription(models.Model):
    name = models.CharField(max_length=100, unique=True, null=False)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=64, decimal_places=2)
    trial_period = models.PositiveIntegerField(null=True, blank=True)
    trial_unit = models.CharField(max_length=1, null=True,
                                       choices = ((None, ugettext_lazy("No trial")),)
                                       + _TIME_UNIT_CHOICES)
    recurrence_period = models.PositiveIntegerField(null=True, blank=True)
    recurrence_unit = models.CharField(max_length=1, null=True,
                                       choices = ((None, ugettext_lazy("No recurrence")),)
                                       + _TIME_UNIT_CHOICES)
    group = models.ForeignKey(auth.models.Group, null=False, blank=False, unique=False)

    _PLURAL_UNITS = {
        'D': 'days',
        'W': 'weeks',
        'M': 'months',
        'Y': 'years',
        }

    class Meta:
        ordering = ('price','-recurrence_period')

    def __unicode__(self): return self.name

    def price_per_day(self):
        """Return estimate subscription price per day, as a float.

        This is used to charge difference when user changes
        subscription.  Price returned is an estimate; month length
        used is 30.4368 days, year length is 365.2425 days (averages
        including leap years).  One-time payments return 0.
        """
        if self.recurrence_unit is None:
            return 0
        return float(self.price) / (
            self.recurrence_period*_recurrence_unit_days[self.recurrence_unit]
            )

    @models.permalink
    def get_absolute_url(self):
        return ( 'subscription_detail', (), dict(object_id=str(self.id)) )

    def get_pricing_display(self):
        if not self.price: return u'Free'
        elif self.recurrence_period:
            return ungettext('%(price).02f / %(unit)s',
                             '%(price).02f / %(period)d %(unit_plural)s',
                             self.recurrence_period) % {
                'price':self.price,
                'unit':self.get_recurrence_unit_display(),
                'unit_plural':_(self._PLURAL_UNITS[self.recurrence_unit],),
                'period':self.recurrence_period,
                }
        else: return _('%(price).02f one-time fee') % { 'price':self.price }

    def get_trial_display(self):
        if self.trial_period:
            return ungettext('One %(unit)s',
                             '%(period)d %(unit_plural)s',
                             self.trial_period) % {
                'unit':self.get_trial_unit_display().lower(),
                'unit_plural':_(self._PLURAL_UNITS[self.trial_unit],),
                'period':self.trial_period,
                }
        else:
            return _("No trial")

# add User.get_subscription() method
def __user_get_subscription(user):
    if not hasattr(user, '_subscription_cache'):
        sl = Subscription.objects.filter(group__in=user.groups.all())[:1]
        if sl: user._subscription_cache = sl[0]
        else: user._subscription_cache = None
    return user._subscription_cache
auth.models.User.add_to_class('get_subscription', __user_get_subscription)


class ActiveUSManager(models.Manager):
    """Custom Manager for UserSubscription that returns only live US objects."""
    def get_query_set(self):
        return super(ActiveUSManager, self).get_query_set().filter(active=True)

class UserSubscription(models.Model):
    user = models.ForeignKey(auth.models.User)
    subscription = models.ForeignKey(Subscription)
    expires = models.DateField(null = True, default=datetime.date.today)
    active = models.BooleanField(default=True)
    cancelled = models.BooleanField(default=True)

    objects = models.Manager()
    active_objects = ActiveUSManager()

    grace_timedelta = datetime.timedelta(
        getattr(settings, 'SUBSCRIPTION_GRACE_PERIOD', 2))

    class Meta:
        unique_together = ( ('user','subscription'), )

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
        if self.expired() or not self.active: return not self.user_is_group_member()
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
            if self.expired() or not self.active:
                self.unsubscribe()
                Transaction(user=self.user, subscription=self.subscription, ipn=None,
                            event='subscription expired'
                            ).save()
                if self.cancelled:
                    self.delete()
                    Transaction(user=self.user, subscription=self.subscription, ipn=None,
                                event='remove subscription (expired)'
                                ).save()
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
            if self.active and self.cancelled: return None # allow resubscribing
            return [ _(u'This is your current subscription.') ]
        return [
            res[1]
            for res in signals.change_check.send(
                self, subscription=subscription)
            if res[1] ]

    @models.permalink
    def get_absolute_url(self):
        return ( 'subscription_usersubscription_detail',
                 (), dict(object_id=str(self.id)) )

    def __unicode__(self):
        rv = u"%s's %s" % ( self.user, self.subscription )
        if self.expired():
            rv += u' (expired)'
        return rv

def unsubscribe_expired():
    """Unsubscribes all users whose subscription has expired.

    Loops through all UserSubscription objects with `expires' field
    earlier than datetime.date.today() and forces correct group
    membership."""
    for us in UserSubscription.objects.get(expires__lt=datetime.date.today()):
        us.fix()

#### Handle PayPal signals

def _ipn_usersubscription(payment):
    class PseudoUS(object):
        pk = None
        def __nonzero__(self): return False
        def __init__(self, user, subscription):
            self.user = user
            self.subscription = subscription

    try: s = Subscription.objects.get(id=payment.item_number)
    except Subscription.DoesNotExist: s = None

    try: u = auth.models.User.objects.get(id=payment.custom)
    except auth.models.User.DoesNotExist: u = None

    if u and s:
        try: us = UserSubscription.objects.get(subscription=s, user=u)
        except UserSubscription.DoesNotExist:
            us = UserSubscription(user=u, subscription=s, active=False)
            Transaction(user=u, subscription=s, ipn=payment,
                        event='new usersubscription', amount=payment.mc_gross
                        ).save()
    else: us = PseudoUS(user=u,subscription=s)

    return us

def handle_payment_was_successful(sender, **kwargs):
    us = _ipn_usersubscription(sender)
    u, s = us.user, us.subscription
    if us:
        if not s.recurrence_unit:
            if sender.mc_gross == s.price:
                us.subscribe()
                us.expires = None
                us.active = True
                us.save()
                Transaction(user=u, subscription=s, ipn=sender,
                            event='one-time payment', amount=sender.mc_gross
                            ).save()
                signals.signed_up.send(s, ipn=sender, subscription=s, user=u,
                                       usersubscription=us)
            else:
                Transaction(user=u, subscription=s, ipn=sender,
                            event='incorrect payment', amount=sender.mc_gross
                            ).save()
                signals.event.send(s, ipn=sender, subscription=s, user=u,
                                   usersubscription=us, event='incorrect payment')
        else:
            if sender.mc_gross == s.price:
                us.extend()
                us.save()
                Transaction(user=u, subscription=s, ipn=sender,
                            event='subscription payment', amount=sender.mc_gross
                            ).save()
                signals.paid.send(s, ipn=sender, subscription=s, user=u,
                                  usersubscription=us)
            else:
                Transaction(user=u, subscription=s, ipn=sender,
                            event='incorrect payment', amount=sender.mc_gross
                            ).save()
                signals.event.send(s, ipn=sender, subscription=s, user=u,
                                   usersubscription=us, event='incorrect payment')
    else:
        Transaction(user=u, subscription=s, ipn=sender,
                    event='unexpected payment', amount=sender.mc_gross
                    ).save()
        signals.event.send(s, ipn=sender, subscription=s, user=u, event='unexpected_payment')
ipn.signals.payment_was_successful.connect(handle_payment_was_successful)

def handle_payment_was_flagged(sender, **kwargs):
    us = _ipn_usersubscription(sender)
    u, s = us.user, us.subscription
    Transaction(user=u, subscription=s, ipn=sender,
                event='payment flagged', amount=sender.mc_gross
                ).save()
    signals.event.send(s, ipn=sender, subscription=s, user=u, event='flagged')
ipn.signals.payment_was_flagged.connect(handle_payment_was_flagged)

def handle_subscription_signup(sender, **kwargs):
    us = _ipn_usersubscription(sender)
    u, s = us.user, us.subscription
    if us:
        # deactivate or delete all user's other subscriptions
        for old_us in u.usersubscription_set.all():
            if old_us==us: continue     # don't touch current subscription
            if old_us.cancelled:
                old_us.delete()
                Transaction(user=u, subscription=s, ipn=sender,
                            event='remove subscription (deactivated)', amount=sender.mc_gross
                            ).save()
            else:
                old_us.active = False
                old_us.unsubscribe()
                old_us.save()
                Transaction(user=u, subscription=s, ipn=sender,
                            event='deactivated', amount=sender.mc_gross
                            ).save()

        # activate new subscription
        us.subscribe()
        us.active = True
        us.cancelled = False
        us.save()
        Transaction(user=u, subscription=s, ipn=sender,
                    event='activated', amount=sender.mc_gross
                    ).save()

        signals.subscribed.send(s, ipn=sender, subscription=s, user=u,
                                usersubscription=us)
    else:
        Transaction(user=u, subscription=s, ipn=sender,
                    event='unexpected subscription', amount=sender.mc_gross
                    ).save()
        signals.event.send(s, ipn=sender, subscription=s, user=u,
                           event='unexpected_subscription')
ipn.signals.subscription_signup.connect(handle_subscription_signup)

def handle_subscription_cancel(sender, **kwargs):
    us = _ipn_usersubscription(sender)
    u, s = us.user, us.subscription
    if us.pk is not None:
        if not us.active:
            us.unsubscribe()
            us.delete()
            Transaction(user=u, subscription=s, ipn=sender,
                        event='remove subscription (cancelled)', amount=sender.mc_gross
                        ).save()
        else:
            us.cancelled = True
            us.save()
            Transaction(user=u, subscription=s, ipn=sender,
                        event='cancel subscription', amount=sender.mc_gross
                        ).save()
        signals.unsubscribed.send(s, ipn=sender, subscription=s, user=u,
                                  usersubscription=us,
#                                  refund=refund, reason='cancel')
                                  reason='cancel')
    else:
        Transaction(user=u, subscription=s, ipn=sender,
                    event='unexpected cancel', amount=sender.mc_gross
                    ).save()
        signals.event.send(s, ipn=sender, subscription=s, user=u, event='unexpected_cancel')
ipn.signals.subscription_cancel.connect(handle_subscription_cancel)
ipn.signals.subscription_eot.connect(handle_subscription_cancel)

def handle_subscription_modify(sender, **kwargs):
    us = _ipn_usersubscription(sender)
    u, s = us.user, us.subscription
    print 'modify', u, s
    if us:
        # delete all user's other subscriptions
        for old_us in u.usersubscription_set.all():
            if old_us==us: continue     # don't touch current subscription
            old_us.delete()
            Transaction(user=u, subscription=s, ipn=sender,
                        event='remove subscription (deactivated)', amount=sender.mc_gross
                        ).save()

        # activate new subscription
        us.subscribe()
        us.active = True
        us.cancelled = False
        us.save()
        Transaction(user=u, subscription=s, ipn=sender,
                    event='activated', amount=sender.mc_gross
                    ).save()

        signals.subscribed.send(s, ipn=sender, subscription=s, user=u,
                                usersubscription=us)
    else:
        Transaction(user=u, subscription=u, ipn=sender,
                    event='unexpected subscription modify', amount=sender.mc_gross
                    ).save()
        signals.event.send(s, ipn=sender, subscription=s, user=u,
                           event='unexpected_subscription_modify')
ipn.signals.subscription_modify.connect(handle_subscription_modify)
