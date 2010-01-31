import datetime
import calendar

def extend_date_by(date, amount, unit):
    """Extend date `date' by `amount' of time units `unit'.

    `unit' can by 'D' for days, 'W' for weeks, 'M' for months or 'Y'
    for years.

    >>> extend_date_by(datetime.date(2007,04,03),5,'Y')
    datetime.date(2012, 4, 3)

    >>> extend_date_by(datetime.date(2007,04,03),5,'M')
    datetime.date(2007, 9, 3)
    >>> extend_date_by(datetime.date(2007,7,3),5,'M')
    datetime.date(2007, 12, 3)
    >>> extend_date_by(datetime.date(2007,8,3),5,'M')
    datetime.date(2008, 1, 3)
    >>> subscription.utils.extend_date_by(datetime.date(2007,10,3),5,'M')
    datetime.date(2008, 3, 3)
    
    >>> subscription.utils.extend_date_by(datetime.date(2007,10,3),1,'W')
    datetime.date(2007, 10, 10)
    >>> subscription.utils.extend_date_by(datetime.date(2007,10,3),2,'W')
    datetime.date(2007, 10, 17)
    >>> subscription.utils.extend_date_by(datetime.date(2007,10,3),5,'W')
    datetime.date(2007, 11, 7)
    >>> subscription.utils.extend_date_by(datetime.date(2007,12,3),5,'W')
    datetime.date(2008, 1, 7)

    >>> subscription.utils.extend_date_by(datetime.date(2007,10,3),29,'D')
    datetime.date(2007, 11, 1)
    >>> subscription.utils.extend_date_by(datetime.date(2007,10,7),29,'D')
    datetime.date(2007, 11, 5)
    >>> subscription.utils.extend_date_by(datetime.date(2007,10,7),99,'D')
    datetime.date(2008, 1, 14)
    >>> subscription.utils.extend_date_by(datetime.date(2007,12,3),5,'D')
    datetime.date(2007, 12, 8)
    >>> subscription.utils.extend_date_by(datetime.date(2007,12,30),5,'D')
    datetime.date(2008, 1, 4)

    >>> subscription.utils.extend_date_by(datetime.date(2007,10,7),99,'Q')
    Traceback (most recent call last):
       ...
    Unknown unit.
    """
    if unit == 'D':
        return date + datetime.timedelta(1)*amount
    elif unit == 'W':
        return date + datetime.timedelta(7)*amount
    elif unit == 'M':
        y, m, d = date.year, date.month, date.day
        m += amount
        y += m / 12
        m %= 12
        if not m: m, y = 12, y-1
        r = calendar.monthrange(y, m)[1]
        if d > r:
            d = r
        return datetime.date(y, m, d)
    elif unit == 'Y':
        y, m, d = date.year, date.month, date.day
        return datetime.date(y+amount, m, d)
    else: raise "Unknown unit."
