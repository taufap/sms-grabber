#!/usr/bin/env python

"""
Google App Engine handler for incoming text messages. Includes very basic retrieval interface.

Licensed under the terms of the Apache License, Version 2.0 (Murray Andrews 2013)
"""

import datetime
import logging
import webapp2

from google.appengine.ext import db
from google.appengine.ext import deferred

from gutils import DbModel, RequestHandler, duration_to_seconds, gae_app_init
from configy import C_RESPONSE, C_MAX_OUT, C_PROVIDER
from db_ops import delete_old_messages

# A_** are URL parameter names. Not used for inbound messages as the
# format of these vary between SMS providers
A_AGE = 'age'
A_COUNT = 'count'
A_DST = 'dst'
A_FMT = 'fmt'
A_ORDERBY = 'orderby'

# Valid output formats for query response.
validFormats = {
    'xml': 'application/xml',
    'json': 'application/json'
}

MAX_OUT = 5000      # Maximum number of messages to retrieve at a time (/out). The actual
                    # number of messages received can be specified in config.yaml and in
                    # the parameters to the /out call but is never larger than this.


#-------------------------------------------------------------------------------
class MsgInHandler(RequestHandler):
    """
    Handler for inbound text messages from all providers that use the standard
    config.yaml driven API style.
    """

    #----------------------------------------------------------------------
    def post(self):
        """
        Handle HTTP POST for incoming text messages. The format of the posted parameters
        is determined by config.yaml.

        Note that by the time this function is called, self.config has been populated
        with the configuration specific to the given inbound SMS provider as loaded from
        congig.yaml. (This is done in __init__ of the superclass RequestHandler).
        """

        # Don't need to do anything different for a POST from a GET. The params just
        # get supplied in the request in a different way but all that is hidden in
        # self.get_params().

        self.get()

    #----------------------------------------------------------------------
    def get(self):
        """
        Handle HTTP GET for incoming text messages. The format of the parameter string is
        determined by config.yaml.

        Note that by the time this function is called, self.config has been populated
        with the configuration specific to the given inbound SMS provider as loaded from
        congig.yaml. (This is done in __init__ of the superclass RequestHandler).

        """

        #----------------------------------------
        # Check source IP address
        self.validate_source_addr()

        #----------------------------------------
        # Check HTTP method is allowed.
        self.validate_method()

        #----------------------------------------
        # Extract and validate query params
        params = self.get_params()

        if params:
            params = self.add_fields(params)

        #----------------------------------------
        # Create TxtMsg object and store it in the Google App Engine datastore
        m = None
        if params:
            m = TxtMsg(
                src=params.get('src'),
                dst=params.get('dst'),
                msg=params.get('msg'),
                provider=self.config.get(C_PROVIDER, '----'),
                sent=params.get('sent'),
                recv=params.get('recv'),
                expiry=params.get('expiry'),
                ip=self.request.remote_addr)
            try:
                m.put()
            except Exception as e:
                logging.error('Message store failed: {}'.format(e))
                self.abort(500, explanation='Message store failed')

        self.response.set_status(200)
        self.response.headers['Content-Type'] = 'text/plain'

        if C_RESPONSE in self.config and self.config[C_RESPONSE]:
            self.w(self.config[C_RESPONSE])

        #----------------------------------------
        # If debug, echo the new record back in the response in XML
        if self.debug:
            self.w()
            if m:
                self.w(m.to_xml())
            else:
                self.w('Nothing stored')


#-------------------------------------------------------------------------------
class MsgOutHandler(RequestHandler):
    """
    Handler to retrieve msg entries from the datastore.
    """

    #----------------------------------------------------------------------
    def get(self):
        """
        Handle HTTP get for retrieval of the most recent txt messages for a given destination entity.
        Messages are produced newest first (as determined by orderby parameter)
        URL for the get must be:
            https://.../out/?param=...&params2=...

        Accepted params in the URL are:
        dst:        Destination phone number. Required.
        count:      Retrieve this number of recent messages. Optional. At most MAX_OUT
                    will be retrieved no matter what this is set to.
        age:        Only retrieve messages less than this age (based on stored time). Can be specified
                    as nnnX where nnn is an integer and X is one of w, d, h, m, s. If missing assume
                    's' (seconds). Optional. If not specified then no age limit is imposed.
        orderby:    Messages are sorted by either 'stored' time or 'expiry' time.
        fmt:        Output format. Must be xml or json. Optional.

        Check config.yaml for defaults.
        """

        #----------------------------------------
        # Check source IP address
        self.validate_source_addr()

        #----------------------------------------
        # Extract and validate query params
        params = self.get_params()

        #----------------------------------------
        # Prepare the base query
        orderby = params[A_ORDERBY]
        gql = 'SELECT * FROM TxtMsg WHERE dst = :1 ORDER BY {orderby} DESC'.format(orderby=orderby)
        q = db.GqlQuery(gql, params[A_DST])

        #----------------------------------------
        # Get maximum message age
        fromtime = None
        if params[A_AGE]:
            age = duration_to_seconds(params[A_AGE])
            fromtime = datetime.datetime.utcnow() - datetime.timedelta(seconds=age)

        #----------------------------------------
        # Make sure we can handle the requested output format. This should never fail
        # if config.yaml is setup correcty to only allow supported values.
        if not hasattr(TxtMsg, 'to_' + params[A_FMT]):
            logging.critical('/out cannot handle format {}'.format(params[A_FMT]))
            self.abort(500, explanation='Bad output format')

        # Specify correct MIME type for the response.
        self.response.headers['Content-Type'] = validFormats.get(params[A_FMT], 'text/plain')

        # Create a crude outer wrapper for XML.
        if params[A_FMT] == 'xml':
            self.w('<MessageList>')

        #----------------------------------------
        # Run query and output results
        max_out = self.config.get(C_MAX_OUT, MAX_OUT)

        try:
            for msg in q.run(limit=min(int(params[A_COUNT]), max_out), read_policy=db.STRONG_CONSISTENCY):

                if fromtime and msg.stored < fromtime:
                    # Ignore messages older than the minimum age. Would be good to do this with GQL
                    # but NDB does not support inequality criteria with different sort key.
                    continue

                # Locate the appropriate formatter and write the record
                formatter = getattr(msg, 'to_' + params[A_FMT])
                self.w(formatter())
        except Exception as e:
            logging.error('Message retrieval failed: {}'.format(e))
            self.abort(500, explanation='Message retrieval failed')

        # Close off crude outer wrapper for XML
        if params[A_FMT] == 'xml':
            self.w('</MessageList>')

        self.response.set_status(200)


#-------------------------------------------------------------------------------
class MsgPurgeHandler(RequestHandler):
    """
    Handler to purge old msg entries from the datastore.
    """

    #----------------------------------------------------------------------
    def get(self):
        """
        Handle HTTP get for purging of txt messages older than a specified age.
        URL for the get must be:
            https://.../purge/?param=...&params2=...

        Accepted params in the URL are:
        age:        Only purge messages older than the specified age. Age is
                    determined by message stored time. Format is nnnX whre nnn
                    is an integer and X is w (weeks), d (days), h (hours),
                    m (minutes) or s (seconds). If X is missing then assume
                    seconds. If no age is specified then the default is 48 hours.

        Note that this does not require authentication but for security should only
        be called by Google cron. So app.yaml must contain the following BEFORE the .* handler:

            handlers:
            - url: /purge/?
              script: main.app
              login: admin

        """

        #----------------------------------------
        # Check source IP address - generally run from Google App Engine cron (see cron.yaml)
        self.validate_source_addr()

        # Extract and validate query params
        params = self.get_params()

        # Get the age parameter
        age = duration_to_seconds(params[A_AGE])

        # Do a deferred operation to delete is it may take some time to complete.
        # DB queries have a hard limit of 60 seconds.

        deferred.defer(delete_old_messages, age=age)

        self.response.set_status(200)


#-------------------------------------------------------------------------------
class TxtMsg(DbModel):
    """
    Model for txt message to be stored in app engine datastore
    """
    src = db.StringProperty(required=True)
    dst = db.StringProperty(required=True)
    msg = db.StringProperty(required=True, indexed=False)
    provider = db.StringProperty(required=False)
    ip = db.StringProperty(required=True)
    sent = db.StringProperty(required=False)
    recv = db.StringProperty(required=False)
    expiry = db.DateTimeProperty(required=False)
    stored = db.DateTimeProperty(auto_now_add=True)


#-------------------------------------------------------------------------------
################################################################################
#-------------------------------------------------------------------------------

# Load global config from config.yaml
conf = gae_app_init()

# Start the app
# Note for the URLs the trailing / is optional before the params
app = webapp2.WSGIApplication(
    [
        ('/out/?', MsgOutHandler),
        ('/dump/?', MsgOutHandler),
        ('/purge/?', MsgPurgeHandler),
        ('/in.*/?', MsgInHandler)
    ],
    debug=True,
    config=conf)
