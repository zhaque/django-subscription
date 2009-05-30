from django.conf.urls.defaults import *

from models import Subscription

urlpatterns = patterns('subscription.views',
    (r'^$', 'subscription_list', {}, 'subscription_list'),
    (r'^(?P<object_id>\d+)/$', 'subscription_detail', {}, 'subscription_detail'),
    )

urlpatterns += patterns('',
    (r'^paypal/', include('paypal.standard.ipn.urls')),
    (r'^done/', 'django.views.generic.simple.direct_to_template', dict(template='subscription/subscription_done.html'), 'subscription_done'),
    (r'^cancel/', 'django.views.generic.simple.direct_to_template', dict(template='subscription/subscription_cancel.html'), 'subscription_cancel'),
    )
