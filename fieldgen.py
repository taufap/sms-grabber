"""
Functions to generate additional fields from a parameter dictionary or to update
existing fields.

Licensed under the terms of the Apache License, Version 2.0 (Murray Andrews 2013)
"""

import re
import datetime


#noinspection PyUnusedLocal
def fg_otp_expiry(params, field_config):
    """
    Extract the OTP expiry time from the message string and add it the params.

    :param params:          Dictionary of params from the incoming request
    :param field_config:    Specifies the field config read from config.yaml. May or may not
                            be needed but must be supplied for all of these fg_* functions.

    :return:            The generated value. No promises regarding type.

    :raises:            ValueError if anything goes wrong.
    """

    expiry_regex = r'.*use it by\s+(?P<expiry>.*?)\s+Singapore'
    expiry_date_fmt = '%H:%M:%S %d/%m/%Y'  # e.g. '17:17:28 01/10/2013'

    if 'msg' not in params:
        raise ValueError('No msg parameter in fg_otp_expiry')

    find = re.search(expiry_regex, params['msg'])
    if not find:
        raise ValueError('fg_otp_expiry could not locate OTP expiry time in message')

    expiry_s = find.group('expiry')
    expiry_time = datetime.datetime.strptime(expiry_s, expiry_date_fmt)

    return expiry_time
