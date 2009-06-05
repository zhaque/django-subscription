from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.sites.models import Site
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.shortcuts import render_to_response, get_object_or_404
from django.views.generic.list_detail import object_list
from django.views.generic.simple import direct_to_template

_formclass = getattr(settings, 'SUBSCRIPTION_PAYPAL_FORM', 'paypal.standard.forms.PayPalPaymentsForm')
_formclass_dot = _formclass.rindex('.')
_formclass_module = __import__(_formclass[:_formclass_dot], {}, {}, [''])
PayPalForm = getattr(_formclass_module, _formclass[_formclass_dot+1:])

from models import Subscription

def _paypal_form_args(**kwargs):
    "Return PayPal form arguments derived from kwargs."
    def _url(rel):
        if not rel.startswith('/'): rel = '/'+rel
        return 'http://%s%s' % ( Site.objects.get_current().domain, rel )

    rv = settings.SUBSCRIPTION_PAYPAL_SETTINGS.copy()
    rv.update( notify_url = _url(reverse('paypal-ipn')),
               return_url = _url(reverse("subscription_done")),
               cancel_return = _url(reverse("subscription_cancel")),
               **kwargs)
    return rv

def _paypal_form(subscription, user):
    if not user.is_authenticated: return None
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
                sra=1             # reattempt payment on payment error
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
            object_list = [
                { 'subscription' : s,
                  'form' : _paypal_form(s, request.user) }
                for s in Subscription.objects.all()]))

# login required, since we need a link to PayPal, so we need to have
# registered user
@login_required
def subscription_detail(request, object_id):
    s = get_object_or_404(Subscription, id=object_id)
    return direct_to_template(
        request, template='subscription/subscription_detail.html',
        extra_context=dict(object=s, form=_paypal_form(s, request.user)))
