from django.conf.urls.defaults import *

import views

urlpatterns = patterns('subscription.views',
    (r'^$', 'subscription_list', {}, 'subscription_list'),
    (r'^(?P<object_id>\d+)/$', 'subscription_detail', {}, 'subscription_detail'),
    )

urlpatterns += patterns('',
    (r'^paypal/', include('paypal.standard.ipn.urls')),
    (r'^done/', 'django.views.generic.simple.direct_to_template', dict(template='subscription/subscription_done.html', extra_context=dict(cancel_url=views.cancel_url)), 'subscription_done'),
    (r'^upgrade-done/', 'django.views.generic.simple.direct_to_template', dict(template='subscription/subscription_upgrade_done.html', extra_context=dict(cancel_url=views.cancel_url)), 'subscription_upgrade_done'),
    (r'^cancel/', 'django.views.generic.simple.direct_to_template', dict(template='subscription/subscription_cancel.html'), 'subscription_cancel'),
    )
