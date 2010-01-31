from datetime import date
import calendar

from django.test import TestCase

import subscription.utils

A_LEAP_YEAR = 2012
NOT_A_LEAP_YEAR = 2011

YEARS = (A_LEAP_YEAR, NOT_A_LEAP_YEAR)
MONTHS = xrange(1, 13)

class SubscriptionUtil(TestCase):

    def test_month(self):
        for year in YEARS:
            for month in MONTHS:
                for day in xrange(1, calendar.monthrange(year, month)[0]+1):
                    start = date(year, month, day)
                    try:
                        added = subscription.utils.extend_date_by(start, 1, 'M')
                    except ValueError:
                        raise ValueError("Cannot extend %s by %s months" % (start, 1))

                    if month == 12:
                        self.assertEqual(added.month, 1)
                    else:
                        self.assertEqual(added.month, start.month + 1)
