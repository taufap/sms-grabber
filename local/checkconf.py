#!/usr/bin/env python

"""
Command line utility to do some basic checking on the config.yaml file.

Very rough and ready but functional. Should integrate with gutils.py properly.

Licensed under the terms of the Apache License, Version 2.0  (Murray Andrews 2013)

"""

__author__ = 'ma'

import sys
from configy import *

try:
    # noinspection PyUnresolvedReferences
    import yaml
except ImportError:
    print('Cannot load yaml module - get PyYaml from pyaml.org')
    exit(2)

MAIN_KEYS_MUST = [C_HANDLERS]

# Logging config keys
LOGGING_KEYS_MUST = []
LOGGING_KEYS_CAN = [C_LOG_LEVEL, C_EMAIL]

# Mandatory handler keys
IN_HANDLER_KEYS_MUST = [C_PARAM_SPEC, C_PROVIDER]
IN_HANDLER_KEYS_CAN = [C_PARAM_SPEC, C_IPS, C_RESPONSE, C_FAIL, C_PROVIDER, C_FIELDS, C_METHODS]
OTHER_HANDLER_KEYS_MUST = [C_PARAM_SPEC]
OTHER_HANDLER_KEYS_CAN = [C_PARAM_SPEC, C_IPS, C_MAX_OUT]

# Allowed parameter keys
IN_PARAM_KEYS_CAN = [C_DEFAULT, C_MATCH, C_REQUIRED, C_STORE, C_VALUES]
OTHER_PARAM_KEYS_CAN = [C_DEFAULT, C_MATCH, C_REQUIRED, C_VALUES]

# Log email keys
LOG_EMAIL_KEYS_MUST = [C_EMAIL_TO, C_EMAIL_LEVEL]
LOG_EMAIL_KEYS_CAN = LOG_EMAIL_KEYS_MUST


#-------------------------------------------------------------------------------
def must_have_keys(d, keys, context=None):
    """
    Make sure that the a dictionary has all of the keys in the given list. Prints
    error messages as it goes.

    :param d:       A dictionary.
    :param keys:    A list of keys that must be present.
    :param context: A string that provides context for the error messages.

    :return:        A count of missing keys (errors)

    """

    context = ' in ' + context if context else ''

    errs = 0
    for i in keys:
        if not d or i not in d:
            errs += 1
            print('Error: Missing key "{}"{}'.format(i, context))

    return errs


#-------------------------------------------------------------------------------
def can_have_keys(d, keys, context=None):
    """
    Check that the dictionary d only contains keys from the specified list. Extras
    will result in a warning being printed.

    :param d:       A dictionary.
    :param keys:    A list of keys that can be present.
    :param context: A string that provides context for the error messages.

    :return:        A count of missing keys (errors)

    """

    context = ' in ' + context if context else ''

    warns = 0
    if d:
        for i in d:
            if i not in keys:
                warns += 1
                print('Warning: key "{}"{} is unexpected'.format(i, context))

    return warns


errors = 0
warnings = 0

if len(sys.argv) != 2:
    print >> sys.stderr, 'Usage: {} YAML_FILE'.format(sys.argv[0])
    exit(1)

for fname in sys.argv[1:]:
    print('\nChecking {}...\n'.format(fname))
    try:
        conf = load_config(fname)
    except IOError as e:
        print(e)
        errors += 1
        continue
    except Exception as e:
        print('{}: {}'.format(fname, e))
        errors += 1
        continue

    errors += must_have_keys(conf, MAIN_KEYS_MUST, 'document')

    if C_LOGGING in conf:
        # Check the logging config
        logconf = conf[C_LOGGING]
        errors += must_have_keys(logconf, LOGGING_KEYS_MUST, C_LOGGING)
        warnings += can_have_keys(logconf, LOGGING_KEYS_CAN, C_LOGGING)

        if C_EMAIL in logconf and logconf[C_EMAIL]:
            for mailconf in logconf[C_EMAIL]:
                errors += must_have_keys(mailconf, LOG_EMAIL_KEYS_MUST, C_LOGGING + '.' + C_EMAIL)
                warnings += can_have_keys(mailconf, LOG_EMAIL_KEYS_CAN, C_LOGGING + '.' + C_EMAIL)

    if C_HANDLERS in conf:
        # Check the specs for each handler
        for handler in conf[C_HANDLERS]:
            parent = C_HANDLERS
            handler_data = conf[C_HANDLERS][handler]

            if handler.startswith('in'):
                handler_keys_must = IN_HANDLER_KEYS_MUST
                handler_keys_can = IN_HANDLER_KEYS_CAN
                param_keys_can = IN_PARAM_KEYS_CAN
            else:
                handler_keys_must = OTHER_HANDLER_KEYS_MUST
                handler_keys_can = OTHER_HANDLER_KEYS_CAN
                param_keys_can = OTHER_PARAM_KEYS_CAN

            parent += '.' + handler

            errors += must_have_keys(handler_data, handler_keys_must, parent)
            warnings += can_have_keys(handler_data, handler_keys_can, parent)

            if C_PARAM_SPEC not in handler_data:
                continue

            parent += '.' + C_PARAM_SPEC

            # Check the specs for each parameter
            for param in handler_data[C_PARAM_SPEC]:
                param_data = handler_data[C_PARAM_SPEC][param]
                warnings += can_have_keys(param_data, param_keys_can, parent + '.' + param)

print('{} errors. {} warnings.'.format(errors, warnings))

exit(1 if errors else 0)
