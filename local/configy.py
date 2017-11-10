"""
Load the config.yaml file. Also contains a bunch of constants used for keys in config.yaml

Licensed under the terms of the Apache License, Version 2.0 (Murray Andrews 2013)
"""

__author__ = 'ma'

import yaml

CONFIG_FILE = 'config.yaml'

# The C_* vars are the fixed node names from config.yaml

# Handler related keys
C_DEFAULT = 'default'
C_HANDLERS = 'handlers'
C_IPS = 'allowed_IPs'
C_MATCH = 'match'
C_METHODS = 'methods'
C_METHODS_DEFAULT = {'GET'}   # Default allowed HTTP methods. Must be an iterable.
C_PARAM_SPEC = 'params'
C_REQUIRED = 'required'
C_RESPONSE = 'response'
C_STORE = 'store'
C_VALUES = 'values'
C_FAIL = 'fail_hard'
C_FAIL_DEFAULT = True
C_PROVIDER = 'provider'
C_MAX_OUT = 'max_out'

C_FIELDS = 'fields'
C_F_NAME = 'name'
C_F_GEN = 'generator'
C_F_DEFAULT = 'default'
C_F_REQUIRED = 'required'

# Logging related keys
C_LOGGING = 'logging'
C_LOG_LEVEL = 'level'
C_EMAIL = 'email'
C_EMAIL_TO = 'to'
C_EMAIL_LEVEL = 'level'


def load_config(config_file=CONFIG_FILE):
    """
    Load the config file. Exceptions are allowed to propagate.

    :param config_file:     A YAML file containing the config.
                            See config.yaml for format info.
    :return:                A dict containing the config.
    """

    with open(config_file, 'r') as cfp:
        conf = yaml.safe_load(cfp)

    return conf
