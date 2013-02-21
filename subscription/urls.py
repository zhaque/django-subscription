from django.conf.urls.defaults import *

import django

if django.VERSION < (1, 5, 0):
    import views
    urlpatterns = patterns('',
        (r'^$', 'subscription.views.subscription_list', {}, 'subscription_list'),
        (r'^done/', 'django.views.generic.simple.direct_to_template',
            dict(template='subscription/subscription_done.html'), 'subscription_done'),
        (r'^change-done/', 'django.views.generic.simple.direct_to_template',
            dict(template='subscription/subscription_change_done.html',
            extra_context=dict(cancel_url=views.cancel_url)), 'subscription_change_done'),
        (r'^cancel/', 'django.views.generic.simple.direct_to_template',
            dict(template='subscription/subscription_cancel.html'), 'subscription_cancel'),
    )
else:
    print "2"
    from django.views.generic import TemplateView
    urlpatterns = patterns('subscription.views',
        url(r'^$', TemplateView.as_view(template_name='subscription/subscription_list.html'), name='subscription_list'),
        url(r'^done/', TemplateView.as_view(template_name='subscription/subscription_done.html'), name='subscription_done'),
        url(r'^change-done/', TemplateView.as_view(template_name='subscription/subscription_change_done.html'), name='subscription_change_done'),
        url(r'^cancel/', TemplateView.as_view(template_name='subscription/subscription_cancel.html'), name='subscription_cancel'),
    )

urlpatterns += patterns('subscription.views',
    (r'^(?P<object_id>\d+)/$', 'subscription_detail', {}, 'subscription_detail'),
    (r'^(?P<object_id>\d+)/(?P<payment_method>(standard|pro))/$', 'subscription_detail', {}, 'subscription_detail'),
    )

urlpatterns += patterns('',
    (r'^paypal/', include('paypal.standard.ipn.urls')),
)
