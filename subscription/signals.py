from django.dispatch import Signal

## Our signals

# one time subscriptions
signed_up = Signal()

# recurring subscriptions
subscribed = Signal()
unsubscribed = Signal()
paid = Signal()

# misc events
event = Signal()
