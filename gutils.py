"""
General utilities for Google App Engine.

Licensed under the terms of the Apache License, Version 2.0  (Murray Andrews 2013)
"""

__author__ = 'ma'

import collections
import json
import re
import logging
from gae_logging import get_log_level, GapMailLoggingHandler

import webapp2
from google.appengine.ext import db

import ipaddr

from configy import *

import fieldgen

LOG_LEVEL = logging.INFO


#-------------------------------------------------------------------------------
class DbModel(db.Model):
    """
    Augmented version of db.Model with some general utilities for db.Models.
    """

    #----------------------------------------------------------------------
    def to_json(self):
        """
        Convert the properties to JSON. Non serialisable properties are converted to a string first.
        Kludgy and inefficient but close enough.

        :return:    JSON formatted string.
        """

        dd = {}

        for prop in self.__class__.properties():
            try:
                # Check if this property can be serialised
                json.dumps(getattr(self, prop))
            except TypeError:
                # Not serialisable - convert to string and hope its close enough
                dd[prop] = str(getattr(self, prop))
            else:
                # Serialisable - use it as is
                dd[prop] = getattr(self, prop)

        return json.dumps(dd)


#-------------------------------------------------------------------------------
class RequestHandler(webapp2.RequestHandler):
    """
    webapp2.RequestHandler augmented with some general utilities for handlers.
    """

    #----------------------------------------------------------------------
    def __init__(self, *args, **kwargs):
        """
        Setup _config and call superclass initialiser.

        :param args:    Positional args
        :param kwargs:  Keyword args
        """

        super(RequestHandler, self).__init__(*args, **kwargs)
        self._config = None

    @property
    def path(self):
        """
        Extract the path for this request.

        :return:    The path for this request, stripped of leading and trailing '/'.
        """

        return self.request.path.strip('/')

    #----------------------------------------------------------------------
    @property
    def config(self):
        """
        Extract the config dictionary provided for this handler from config.yaml.
        Aborts with various HTTP errors if config cannot be found.

        :return:    Config dictionary. See config.yaml for more info.
        """

        if self._config:
            return self._config

        if C_HANDLERS not in self.app.config:
            logging.critical('No handlers configured - check config.yaml')
            self.abort(500, explanation='No handlers configured')

        # Determine which path was invoked and if we can handle it.
        if self.path not in self.app.config[C_HANDLERS]:
            err = 'Invalid path "{}"'.format(self.path)
            logging.error(err)
            self.abort(404, explanation=err)

        self._config = self.app.config[C_HANDLERS][self.path]
        return self._config

    #----------------------------------------------------------------------
    @property
    def debug(self):
        """
        Check if debug parameter is specified in the URL parameters.

        :return:    True if debug is present. False otherwise.
        """
        return 'debug' in self.request.params

    #----------------------------------------------------------------------
    def validate_source_addr(self, allowed_addrs=None):
        """
        Validate the source IP address for the request. Returns nothing if ok.
        Aborts with HTTP error 403 (Forbidden) if source is invalid.

        :param allowed_addrs:   An IP4/IP6 address range which can be any of
                                the following:
                                - A single IP address in dot (IP4) or colon (IP6)
                                  notation
                                - A CIDR format for IP4 or IP6 (e.g. 192.168.1.0/24)
                                - An iterable of items from above (typically, a
                                  list or set). The source IP can be in any of
                                  the ones in the iterable.
                                If None then use the allowed_IPs entry from the
                                config. If an empty list is supplied then the
                                source IP address is deemed OK.

        """

        if allowed_addrs is None:
            allowed_addrs = self.config.get(C_IPS)

        ip = self.request.remote_addr
        if allowed_addrs and not ipaddr.ip_match(ip, allowed_addrs):
            # HTTP 403 == Forbidden
            logging.error('Invalid source address: ' + ip)
            self.abort(403, explanation='Invalid source address: ' + ip)

    #----------------------------------------------------------------------
    def validate_method(self, allowed_methods=None):
        """
        Validate the HTTP method used for the request. Returns nothing if ok.
        Aborts with HTTP error 405 (Method Not Allowed). This is not considered
        an error as such and will only generate an INFO level log message.
        This is because some clients will first try a POST and then a GET and
        we don't want an error message for every call.

        :param allowed_methods: An iterable of strings listing allowed HTTP
                                methods (GET or POST)
        """

        if allowed_methods is None:
            allowed_methods = self.config.get(C_METHODS, C_METHODS_DEFAULT)

        if not allowed_methods:
            allowed_methods = C_METHODS_DEFAULT

        method = self.request.method.upper()

        if method not in allowed_methods:
            logging.info('Invalid method {} from {}'.format(method, self.request.remote_addr))
            self.abort(405, explanation='Method Not Allowed')

    #----------------------------------------------------------------------
    def get_params(self, api_spec=None):
        """
        Extract the parameter fields from a HTTP request and validate them. For a
        HTTP GET the parameters are encoded in the URL itself (as a URL encoded
        string appended to the base resource + '?'). For a HTTP POST the parameters
        are encoded as a URL encoded string in the posted data.

        Unexpected arguments are ignored.

        :param api_spec:    A dictionary of parameter specs that describe the API
                            accepted by a given web resource. If None then try to
                            extract it from the handler config. See config.yaml.
                            For inbound SMS handlers, this describes the API of
                            the service provider. The parameter values provided
                            when invoking the resource must satisfy the API spec.

        :return:            Return a dictionary of validated values (all values
                            are either strings or None) or return None if fail_hard
                            is False and a value fails validation. Keys are parameter
                            names but note that these may differ from the incoming
                            parameter names as config.yaml allows renaming using the
                            "store" (C_STORE) field in the API spec.
        """

        if api_spec is None:
            if C_PARAM_SPEC not in self.config:
                logging.critical(
                    'No API specification for path "{}" - check config.yaml'.format(self.path))
                self.abort(500, explanation='No API specification')
            api_spec = self.config[C_PARAM_SPEC]

        fail_hard = self.config.get(C_FAIL, C_FAIL_DEFAULT)

        validated_param_vals = {}

        #---------------------------------------
        # Loop through all the params specified in the parameter specifications (i.e. the API config)
        for param_type in api_spec:

            param_spec = api_spec[param_type]
            param_default = param_spec.get(C_DEFAULT)

            # Get the parameter value supplied to the current invocation of the resource
            # for the specified parameter type.
            try:
                param_val = self.request.get(param_type, param_default)
            except UnicodeDecodeError as e:
                logging.error('Decode error for param {}: {}'.format(param_type, e))
                param_val = '* Undecodeable unicode *'

            if param_val:
                param_val = str(param_val)

            # Make sure mandatory parameters have been supplied.
            if not param_val and param_spec.get(C_REQUIRED, False):
                err = 'Parameter "{}": required but missing'.format(param_type)
                logging.error(err)
                self.abort(400, explanation=err)

            # Validate / extract values as required in config.yaml. Note that we flatten
            # allowedValues into a single list. This allows weird heirarchies of values
            # in config.yaml to be processed correctly.

            if param_val is not None:
                new_val = validate_str(param_val,
                                       match_pattern=param_spec.get(C_MATCH),
                                       allowed_values=list(flatten(param_spec.get(C_VALUES))))

                if new_val is None:
                    err = 'Parameter "{}": Value "{}" failed validation'.format(param_type, param_val)
                    if fail_hard:
                        logging.error(err)
                        self.abort(400, explanation=err)
                    else:
                        logging.warning(err)
                        return None
                else:
                    param_val = new_val

            # Parameter has validated ok - now see if we needed to extract a matching subcomponent

            # Get the canonical name for this param type. This allows params
            # with different names in various APIs to be mapped to a common name.
            param_name = param_spec.get(C_STORE, param_type)

            validated_param_vals[param_name] = param_val

        return validated_param_vals

    #----------------------------------------------------------------------
    # TODO:   This whole notion is misguided and was done in a hurry to address immediate issue.
    def add_fields(self, params, field_config=None):
        """
        Add any derived fields to the params.

        :param params:          The parameters dictionary for the request.
        :param field_config:    The field configuration from config.yaml. Basically a list of dicts.
                                Each dict can contain a field name and the name of a generator function
                                to derive the value, typically from existing parameters and fields.
        :return:                The augmented params dict.
        """

        if field_config is None:
            field_config = self.config.get(C_FIELDS)

        if not field_config:
            # Nothing to do
            return params

        fail_hard = self.config.get(C_FAIL, C_FAIL_DEFAULT)

        for field in field_config:
            if C_F_NAME not in field:
                logging.critical(
                    'Missing field name in config for path "{}" - check config.yaml'.format(self.path))
                self.abort(500, explanation='Field name missing')

            field_val = None

            #---------------------------------------
            # Check for a generator
            if C_F_GEN in field:
                # A generator is specified - see if we can find it
                if not hasattr(fieldgen, field[C_F_GEN]):
                    logging.critical(
                        'Cannot locate generator {} for path "{}"'.format(field[C_F_GEN], self.path))
                    self.abort(500, explanation='Missing field generator')

                generator = getattr(fieldgen, field[C_F_GEN])

                try:
                    field_val = generator(params, field)
                except Exception as e:
                    err = 'Field generator {} failed: {}'.format(field[C_F_GEN], e)
                    if fail_hard:
                        logging.error(err)
                        self.abort(400, explanation=err)
                    else:
                        logging.warning(err)
                        return None

            #---------------------------------------
            # If no value, try for a default
            if not field_val and C_F_DEFAULT in field:
                field_val = field[C_F_DEFAULT]

            #---------------------------------------
            # Check that required values are present
            if C_F_REQUIRED in field and field[C_F_REQUIRED] and not field_val:
                # Need a value but don't have one
                err = 'Required field "{}" has no value'.format(field[C_F_NAME])
                if fail_hard:
                    logging.error(err)
                    self.abort(400, explanation=err)
                else:
                    logging.warning(err)
                    return None

            params[field[C_F_NAME]] = field_val

        return params
                
    #----------------------------------------------------------------------
    def w(self, *s):
        """
        Join the arguments with spaces and write them to the response followed by newline.

        :param s:  Arguments - will be converted to strings

        """

        ss = [str(t) for t in s]
        self.response.write(' '.join(ss) + '\n')


#-------------------------------------------------------------------------------
def validate_str(value, allowed_values=None, match_pattern=None, validator_fn=None):
    """
    Validate a supplied string. Validation can be performed against a regex or a
    list of permitted values or by running a provided validation function. If more
    than one validator is provided then they are applied in the following order
    and the value must pass all of them:
        1. match_pattern
        2. validator_fn
        3. allowed_values
    Both the match_pattern and the validator_fn can alter the value (see parameter
    descriptions). If no validator is supplied then the value passes by default.

    :param value:           The string to validate
    :param allowed_values:  A list, set or tuple containing allowed values. If None
                            or empty then any value is permitted. Default None.
    :param match_pattern:   A regex which value must match (using re.match()). Can
                            contain a capture group which will replace the value.
                            Default None.
    :param validator_fn:    A function that takes value as its only argument the
                            (possibly modified) value if everything is OK or
                            otherwise None. Default None.

    :return:                The (possibly modified) value or None if validation
                            failed.
    """

    if not isinstance(value, str):
        raise TypeError('validate_value expected string and got {}'.format(type(value)))

    if match_pattern:
        m = re.match(match_pattern, value)
        if not m:
            return None

        if m.groups():
            # Extract the matching group
            value = m.group(1)

    if validator_fn:
        value = validator_fn(value)
        if not value:
            return None

    if allowed_values and value not in allowed_values:
        return None

    return value


#-------------------------------------------------------------------------------
time_units = {
    'w': 60 * 60 * 24 * 7,
    'd': 60 * 60 * 24,
    'h': 60 * 60,
    'm': 60,
    's': 1,
    '': 1  # Default is seconds
}

DURATION_REGEX = r'\s*(?P<value>\d+)\s*(?P<units>[{units}]?)\s*$'.format(units=''.join(time_units.keys()))


def duration_to_seconds(duration):
    """
    Convert a string specifying a time duration to a number of seconds.

    :param duration:    String in the form nnnX where nnn is an integer and X is one of:
                        'w':    weeks
                        'd':    days
                        'h':    hours
                        'm':    minutes
                        's':    seconds.

                        If X is missing then seconds are assumed. Whitespace is ignored.

    :raises:            ValueError if the duration string is malformed.
    """

    m = re.match(DURATION_REGEX, duration)

    if not m:
        raise ValueError('Invalid duration: ' + duration)

    return int(m.group('value')) * time_units[m.group('units')]


#-------------------------------------------------------------------------------
def flatten(l):
    """
    Flatten a possibly nested iterable (e.g. list) into a single level iterable.
    Handling of string and None arguments is a little odd. A string flattens to
    a sequence containing the string and None flattens to an empty sequence.

    :param l:          The iterable to flatten.
    :return:            A generator for the flattened iterator.
    """

    if not l:
        raise StopIteration

    if isinstance(l, basestring):
        yield l
    elif isinstance(l, collections.Iterable):
        for i in l:
            if isinstance(i, collections.Iterable) and not isinstance(i, basestring):
                for sub in flatten(i):
                    yield sub
            else:
                yield i
    else:
        raise ValueError('Cannot flatten non-iterable')


#-------------------------------------------------------------------------------
def gae_app_init(config_file=CONFIG_FILE):
    """
    Initialise some stuff before the app is fully started. Note that this function
    does not actually start the handlers. It loads the config file and sets up
    logging.

    :param config_file:     A YAML file containing config data. Default is config.yaml.

    :return:                The global config dictionary.

    """

    #----------------------------------------------------------------------
    # Set initial logging level. May be subsequently overridden in config.
    logging.getLogger().setLevel(LOG_LEVEL)

    #----------------------------------------------------------------------
    # Load config - let exceptions propagate as we don't have an available response object yet.
    conf = load_config()

    #----------------------------------------------------------------------
    # Setup logging config
    if C_LOGGING in conf:

        #----------------------------------------
        # Set log level
        log_conf = conf[C_LOGGING]

        if log_conf and log_conf.get(C_LOG_LEVEL, None):

            try:
                log_level = get_log_level(log_conf[C_LOG_LEVEL])
            except ValueError as e:
                # Serious but we can plow on rather than fail horribly.
                logging.critical('Error in {}: {}'.format(config_file, e))
            else:
                logging.getLogger().setLevel(log_level)

        #----------------------------------------
        # Setup email config for specified log levels
        if log_conf and log_conf.get(C_EMAIL, None):
            try:
                mail_handler = GapMailLoggingHandler(log_conf[C_EMAIL])
            except ValueError as e:
                logging.critical('Cannot create log handler for mail: {}'.format(e))
            else:
                logging.getLogger().addHandler(mail_handler)

    return conf
