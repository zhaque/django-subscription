import sys
from django.conf import settings

"""
PROPOSALS (only for payment methods which happens behind the scene)

1. New payment methods must be implemented as class (BasePaymentMethod)
2. According to user selected payment method, build object (Factory DP)
3. Call proceed() function.

TODO
1. Create mappings <payment_method> => <payment_class> to make views more clear, i.e.:

in urls.py
 (r'^(?P<object_id>\d+)/(?P<payment_method>(standard|pro|authorize))$', 'subscription_detail', {}, 'subscription_detail'),

in settings.py:
PAYMENT_METHODS_MAPPINGS = {
    'pro': 'WebsitePaymentsPro', #subscription.providers.WebsitePaymentsPro
    'authorize': 'Authorize', #subscription.providers.Authorize
    etc..
}

in.views.py:

def subscription_details(request, object_id, payment_method="pro"):
    from subscription.providers import PaymentMethodFactory, pick_class    
    payment_object = PaymentMethodFactory(pick_class(payment_method), ...)    
    payment_object.proceed(...)

"""

def pick_class(payment_method, default_method):
    """
    return settings.PAYMENT_METHODS_MAPPINGS.get(payment_method, default_method)    
    """
    pass


class BasePaymentMethod(object):
    """This class represents the abstract base class for new payment methods"""
    def __init__(self):
        self.name = None
        
    def proceed(self):
        """Runs payment process"""
        pass
        
    def get_name(self):
        """Returns full name of payment method"""
        return self.name    


class PaymentMethodFactory(object):
    """Implementation of Factory Design Pattern"""
    @staticmethod
    def factory(payment_method, **kwargs):
        """ Factory method"""
        cls = getattr(sys.modules[__name__], payment_method)
        return cls(**kwargs)
    

class WebsitePaymentsPro(BasePaymentMethod):
    """Wrapper around django-paypal's PayPalPro"""
    def __init__(self, **kwargs):
        self.name = 'Website Payments Pro'
        self.data = kwargs.get('data')
        self.request = kwargs.get('request')
        
    def proceed(self):
        from paypal.pro.views import PayPalPro
        ppp = PayPalPro(**self.data)
        return ppp(self.request)