#!/usr/bin/env python

"""
Load some SMS messages into the local test rig. The bulk loader pattern is always used.
See also dumper.py which can extract messages from the production database in the correct
format for loader. Use the "raw" format option on dumper.
"""

__author__ = 'ma'

import sys
from os.path import basename
import json
import urllib
import urllib2
import argparse

PROG = basename(sys.argv[0])

LOAD_URL = "http://localhost:8080/in-bulk"
FIELDS = {'src', 'dst', 'msg', 'sent', 'recv', 'expiry'}


#-------------------------------------------------------------------------------
def load_with_get(url, fields):
    """
    Load one record using HTTP GET.

    :param url:         URL to invoke for the load.
    :param fields:      Record fields (dict).

    :returns            Whatever is read back from the the GET.
    """

    full_url = url + "?" + urllib.urlencode(fields)
    response = urllib2.urlopen(full_url)
    r = response.read()
    response.close()
    return r


#-------------------------------------------------------------------------------
def load_with_post(url, fields):
    """
    Load one record using HTTP GET.

    :param url:         URL to invoke for the load.
    :param fields:      Record fields (dict).
    """

    data = urllib.urlencode(fields)

    response = urllib2.urlopen(url, data)
    r = response.read()
    response.close()
    return r


#-------------------------------------------------------------------------------
def main():
    """
    Main load loop
    """

    #---------------------------------------
    # Parse options
    argp = argparse.ArgumentParser(description='Load JSON formatted SMS messages into the local test rig', prog=PROG)
    argp.add_argument('-c', '--count', type=int, default=0,
                      help='Maximum number of messages to load. Default is 0 (load all).')
    argp.add_argument('-p', '--post', action='store_true',
                      help='Use POST instead of GET to load the messages')
    argp.add_argument('-r', '--response', action='store_true',
                      help='Print whatever responses come back from the server instead of load count')
    argp.add_argument('infile', nargs='+', type=argparse.FileType('r'),
                      help='Input files. If - then use stdin.')

    args = argp.parse_args()

    loader = load_with_post if args.post else load_with_get

    #---------------------------------------
    # Load JSON records from input files

    count = 0
    for fp in args.infile:

        for rec_s in fp:

            if 0 < args.count <= count:
                break

            rec_json = json.loads(rec_s)

            # Select the required fields for the URL. Only non-empty values.
            d = {k: v for k, v in rec_json.iteritems() if v and k in FIELDS}

            response = None
            try:
                response = loader(LOAD_URL, d)
            except urllib2.HTTPError as e:
                print >> sys.stderr, e
                print >> sys.stderr, "Abort."
                fp.close()
                exit(2)

            count += 1

            if args.response:
                print(response.strip())
            else:
                print >> sys.stderr, '{:6d} records loaded. Processing {}{}\r'.format(count, fp.name, 30 * ' '),

        fp.close()

    print >> sys.stderr, '{:6d} records loaded.{}'.format(count, 60 * ' ')


if __name__ == '__main__':
    main()
    exit(0)
