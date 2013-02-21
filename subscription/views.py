import urllib

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.sites.models import Site
from django.core.urlresolvers import reverse
from django.shortcuts import render, get_object_or_404
from django.http import Http404
from django.dispatch import Signal

import django
if django.VERSION <= (1, 5, 0):
    from django.views.generic.simple import direct_to_template

_formclass = getattr(settings, 'SUBSCRIPTION_PAYPAL_FORM', 'paypal.standard.forms.PayPalPaymentsForm')
_formclass_dot = _formclass.rindex('.')
_formclass_module = __import__(_formclass[:_formclass_dot], {}, {}, [''])
PayPalForm = getattr(_formclass_module, _formclass[_formclass_dot + 1:])

from models import Subscription, UserSubscription

get_paypal_extra_args = Signal(providing_args=['user', 'subscription', 'extra_args'])

# http://paypaldeveloper.com/pdn/board/message?board.id=basicpayments&message.id=621
if settings.PAYPAL_TEST:
    cancel_url = 'https://www.sandbox.paypal.com/cgi-bin/webscr?cmd=_subscr-find&alias=%s' % urllib.quote(settings.PAYPAL_RECEIVER_EMAIL)
else:
    cancel_url = 'https://www.paypal.com/cgi-bin/webscr?cmd=_subscr-find&alias=%s' % urllib.quote(settings.PAYPAL_RECEIVER_EMAIL)

# Reference document for paypal html variables
# https://cms.paypal.com/us/cgi-bin/?cmd=_render-content&content_ID=developer/e_howto_html_Appx_websitestandard_htmlvariables


def _paypal_form_args(upgrade_subscription=False, **kwargs):
    "Return PayPal form arguments derived from kwargs."
    def _url(rel):
        if not rel.startswith('/'):
            rel = '/' + rel
        return 'http://%s%s' % (Site.objects.get_current().domain, rel)

    if upgrade_subscription:
        returl = reverse('subscription_change_done')
    else:
        returl = reverse('subscription_done')

    rv = settings.SUBSCRIPTION_PAYPAL_SETTINGS.copy()
    rv.update(notify_url=_url(reverse('paypal-ipn')),
              return_url=_url(returl),
              cancel_return=_url(reverse("subscription_cancel")),
              **kwargs)
    return rv


def _paypal_form(subscription, user, upgrade_subscription=False, **extra_args):
    if not user.is_authenticated:
        return None

    if subscription.price <= 0:
        # Handles the scenario when subscription price is set to 0 or negative
        # value.  This means it is a "free plan" and should be handled
        # appropriately by user of this library
        return None
    elif subscription.recurrence_unit:
        if subscription.trial_unit == '0':
            trial = {}
        else:
            trial = {
                'a1': 0,
                'p1': subscription.trial_period,
                't1': subscription.trial_unit,
                }
        kwargs = {}
        kwargs.update(trial)
        kwargs.update(extra_args)
        return PayPalForm(
                initial=_paypal_form_args(
                cmd='_xclick-subscriptions',
                item_name='%s: %s' % (Site.objects.get_current().name, subscription.name),
                item_number=subscription.id,
                custom=user.id,
                a3=subscription.price,
                p3=subscription.recurrence_period,
                t3=subscription.recurrence_unit,
                src=1,            # make payments recur
                sra=1,            # reattempt payment on payment error
                upgrade_subscription=upgrade_subscription,
                # subscription modification (upgrade/downgrade)
                modify=upgrade_subscription and 2 or 0, **kwargs),
                button_type='subscribe'
            )
    else:
        return PayPalForm(
                initial=_paypal_form_args(
                item_name='%s: %s' % (Site.objects.get_current().name, subscription.name),
                item_number=subscription.id,
                custom=user.id,
                amount=subscription.price))


def subscription_list(request):
    return direct_to_template(
        request, template='subscription/subscription_list.html',
        extra_context=dict(object_list=Subscription.objects.all()))


@login_required
def subscription_detail(request, object_id, payment_method="standard"):
    s = get_object_or_404(Subscription, id=object_id)

    try:
        user = request.user.usersubscription_set.get(
            active=True)
    except UserSubscription.DoesNotExist:
        change_denied_reasons = None
        user = None
    else:
        change_denied_reasons = user.try_change(s)

    if change_denied_reasons:
        form = None
    else:
        get_paypal_extra_args.send(sender=None, user=user, subscription=s, extra_args={})
        form = _paypal_form(s, request.user, upgrade_subscription=(user is not None) and (user.subscription != s))

    try:
        s_us = request.user.usersubscription_set.get(subscription=s)
    except UserSubscription.DoesNotExist:
        s_us = None

    from subscription.providers import PaymentMethodFactory
    # See PROPOSALS section in providers.py
    if payment_method == "pro":
        domain = Site.objects.get_current().domain
        item = {"amt": s.price,
                "inv": "inventory",         # unique tracking variable paypal
                "custom": "tracking",       # custom tracking variable for you
                "cancelurl": 'http://%s%s' % (domain, reverse('subscription_cancel')),  # Express checkout cancel url
                "returnurl": 'http://%s%s' % (domain, reverse('subscription_done'))}  # Express checkout return url

        data = {"item": item,
                "payment_template": "payment.html",       # template name for payment
                "confirm_template": "confirmation.html",  # template name for confirmation
                "success_url": reverse('subscription_done')}              # redirect location after success

        o = PaymentMethodFactory.factory('WebsitePaymentsPro', data=data, request=request)
        # We return o.proceed() just because django-paypal's PayPalPro returns HttpResponse object
        return o.proceed()

    elif payment_method == 'standard':
        template_vars = {'object': s,
                         'usersubscription': s_us,
                         'change_denied_reasons': change_denied_reasons,
                         'form': form,
                         'cancel_url': cancel_url}
        template = 'subscription/subscription_detail.html'
        return render(request, template, template_vars)
    else:
        #should never get here
        raise Http404
