"""

Various database related operations

Licensed under the terms of the Apache License, Version 2.0 (Murray Andrews 2013)

"""

__author__ = 'ma'

import datetime
import logging

from google.appengine.ext import db


#-------------------------------------------------------------------------------
def delete_old_messages(age):
    """
    Delete old messages from the database. This can take a while and should be
    run in a task queue or the deferred handler. As such it does its work quietly.
    Problems are logged but no exceptions or return values.

    :param age:         Messages older than this many seconds are deleted. Age is
                        determined by time message was stored in the database.
    """

    fromtime = datetime.datetime.utcnow() - datetime.timedelta(seconds=age)

    #----------------------------------------
    # Run query and loop through results to delete
    del_count = 0
    try:
        q = db.GqlQuery('SELECT * FROM TxtMsg where stored < :1', fromtime)
        for msg in q.run():
            msg.delete()
            del_count += 1
    except Exception as e:
        logging.error('Deferred purge failed: {}'.format(e))

    logging.info('{} records deleted'.format(del_count))
