from django.dispatch import Signal

## Our signals

# one time subscriptions
signed_up = Signal()

# recurring subscriptions
subscribed = Signal()
unsubscribed = Signal()
paid = Signal()

# misc. subscription-related events
event = Signal()

# upgrade/downgrade possibility check
change_check = Signal()
