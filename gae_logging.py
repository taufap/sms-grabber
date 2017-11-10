"""
Log handler class to send log messages to email addresses on Google App Engine.

Licensed under the terms of the Apache License, Version 2.0  (Murray Andrews 2013)
"""
__author__ = 'ma'

import os
import logging
from google.appengine.api import mail
from google.appengine.api import app_identity

import configy
import gutils

MAIL_SENDER = 'logger'


#-------------------------------------------------------------------------------
def get_log_level(s, errmsg='Bad log level'):
    """
    Convert the string version of a log level defined in the logging module to the
    corresponding log level. Raises ValueError if a bad string is provided.

    :param s:               A string version of a log level (e.g. 'error', 'info').
                            Case is not significant.
    :param errmsg:          Used for the ValueError if required. The offending
                            log level string (s) will be appended.

    :return:                The numeric logLevel equivalent.

    :raises:                ValueError if the supplied string cannot be converted.
    """

    if not s or not isinstance(s, str):
        raise ValueError(errmsg + ':' + str(s))

    t = s.upper()

    if not hasattr(logging, t):
        raise ValueError(errmsg + ':' + s)

    return getattr(logging, t)


#-------------------------------------------------------------------------------
class GapMailLoggingHandler(logging.Handler):
    """
    Logging handler for Google App Enginge that sends log messages to email addresses.
    """

    #----------------------------------------------------------------------
    def __init__(self, config):
        """
        Setup the handler with the recipient addresses and what level of messages
        they receive.api.

        :param config:          A list of log message targets. Each element in the list
                                is a dict with 2 components:
                                    - 'level' contains a string version of a log level.api
                                    - 'to' contains either a single email address or a hierarchical
                                      list of addresses.
                                This is exactly the format produced from the config YAML file under
                                the logging.email key. If an element of the list is malformed, that will
                                be logged but otherwise that element in the list is discarded. If the
                                one level occurs more than once in the list only will be preserved.

        :raises ValueError:     If the config is malformed.

        """

        super(GapMailLoggingHandler, self).__init__()

        self.levels_to_addresses = dict()

        # Scan through the config and create a dictionary with a key for each logging level
        # and the target email addresses as values. We don't analyse the addresses here.
        for el in config:
            if not isinstance(el, dict):
                raise ValueError('Non-dictionary component in email-logging configuration')

            if gutils.C_EMAIL_LEVEL not in el or gutils.C_EMAIL_TO not in el:
                raise ValueError('Missing component in email-logging configuration')

            self.levels_to_addresses[get_log_level(el[configy.C_EMAIL_LEVEL])] = el[configy.C_EMAIL_TO]

        # Setup a sender address
        self.app_id = app_identity.get_application_id()
        self.app_ver = os.environ.get('CURRENT_VERSION_ID')
        self.sender = '{}@{}.appspotmail.com'.format(MAIL_SENDER, self.app_id)

    #----------------------------------------------------------------------
    def emit(self, record):
        """
        Send a log record via email (depending on level).

        :param record:          Log record
        """

        recipients = set()

        for email_level in self.levels_to_addresses:
            if record.levelno < email_level:
                continue

            # Need to send this record to the list recipients.
            for email in gutils.flatten(self.levels_to_addresses[email_level]):
                recipients.add(email)

        for r in recipients:
            if mail.is_email_valid(r):
                subject = '{} from {} (Ver {})'.format(record.levelname, self.app_id, self.app_ver)
                body = self.format(record)
                #noinspection PyBroadException
                try:
                    mail.send_mail(self.sender, r, subject, body)
                except Exception:
                    # If we cannot send an email just plow on but don't fail.
                    pass
