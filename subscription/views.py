import datetime, urllib

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.sites.models import Site
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.views.generic.list_detail import object_list
from django.views.generic.simple import direct_to_template

_formclass = getattr(settings, 'SUBSCRIPTION_PAYPAL_FORM', 'paypal.standard.forms.PayPalPaymentsForm')
_formclass_dot = _formclass.rindex('.')
_formclass_module = __import__(_formclass[:_formclass_dot], {}, {}, [''])
PayPalForm = getattr(_formclass_module, _formclass[_formclass_dot+1:])

from models import Subscription, UserSubscription

# http://paypaldeveloper.com/pdn/board/message?board.id=basicpayments&message.id=621
if settings.PAYPAL_TEST:
    cancel_url = 'https://www.sandbox.paypal.com/cgi-bin/webscr?cmd=_subscr-find&alias=%s' % urllib.quote(settings.PAYPAL_RECEIVER_EMAIL)
else:
    cancel_url = 'https://www.paypal.com/cgi-bin/webscr?cmd=_subscr-find&alias=%s' % urllib.quote(settings.PAYPAL_RECEIVER_EMAIL)

def _paypal_form_args(upgrade_subscription=False, **kwargs):
    "Return PayPal form arguments derived from kwargs."
    def _url(rel):
        if not rel.startswith('/'): rel = '/'+rel
        return 'http://%s%s' % ( Site.objects.get_current().domain, rel )

    if upgrade_subscription: returl = reverse('subscription_upgrade_done')
    else: returl = reverse('subscription_done')

    rv = settings.SUBSCRIPTION_PAYPAL_SETTINGS.copy()
    rv.update( notify_url = _url(reverse('paypal-ipn')),
               return_url = _url(returl),
               cancel_return = _url(reverse("subscription_cancel")),
               **kwargs)
    print rv
    return rv

def _paypal_form(subscription, user, rebate=None, upgrade_subscription=False):
    if not user.is_authenticated: return None
    if rebate is not None: print "FIXME: rebate", rebate
    if subscription.recurrence_unit:
        return PayPalForm(
            initial = _paypal_form_args(
                cmd='_xclick-subscriptions',
                item_name='%s: %s' % ( Site.objects.get_current().name,
                                       subscription.name ),
                item_number = subscription.id,
                custom = user.id,
                a3=subscription.price,
                p3=subscription.recurrence_period,
                t3=subscription.recurrence_unit,
                src=1,                  # make payments recur
                sra=1,            # reattempt payment on payment error
                upgrade_subscription=upgrade_subscription
                ),
            button_type='subscribe'
            )
    else:
        return PayPalForm(
            initial = _paypal_form_args(
                item_name='%s: %s' % ( Site.objects.get_current().name,
                                       subscription.name ),
                item_number = subscription.id,
                custom = user.id,
                amount=subscription.price))

def subscription_list(request):
    return direct_to_template(
        request, template='subscription/subscription_list.html',
        extra_context=dict(
            object_list = Subscription.objects.all()))

@login_required
def subscription_detail(request, object_id):
    s = get_object_or_404(Subscription, id=object_id)

    try:
        us = request.user.usersubscription_set.get(
            active=True)
    except UserSubscription.DoesNotExist:
        change_denied_reasons = None
        discount = None
        us = None
    else:
        change_denied_reasons = us.try_change(s)
        unused_days = (us.expires - datetime.date.today()).days
        discount = unused_days * us.subscription.price_per_day()

    if change_denied_reasons: form = None
    else: form = _paypal_form(s, request.user, discount, upgrade_subscription=us is not None)

    try: s_us = request.user.usersubscription_set.get(subscription=s)
    except UserSubscription.DoesNotExist: s_us = None

    return direct_to_template(
        request, template='subscription/subscription_detail.html',
        extra_context=dict(object=s, usersubscription=s_us,
                           change_denied_reasons=change_denied_reasons,
                           form=form, cancel_url=cancel_url))

@login_required
def __subscription_change(request, object_id):
    s = get_object_or_404(Subscription, id=object_id)

    try:
        old_us = request.user.usersubscription
    except UserSubscription.DoesNotExist:
        change_denied_reasons = []
        old_us = None
    else:
        change_denied_reasons = us.try_change(s)

    if change_denied_reasons:
        return direct_to_template(
            request, template='subscription/subscription_change_error.html',
            extra_context=dict(
                subscription=s,
                change_denied_reasons=change_denied_reasons))

    us = UserSubscription(
        user=request.user, subscription=s,
        expires=datetime.date.today() + UserSubscription.grace_timedelta)
    us.save()

    if old_us:
        old_us.active = False
        old_us.save()
        unused_days = (old_us.expires - datetime.date.today()).days
        unused_money = unused_days * old_us.subscription.price_per_day()
        if unused_money > 0:
            pass # USDiscount(usersubscription=us, discount=unused_money).save()

    return HttpResponseRedirect(us.get_absolute_url())
