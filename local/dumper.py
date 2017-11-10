#!/usr/bin/env python

"""
Dump ACS OTP messages from GAE, optionally analysing transit times.

WARNING: Has embedded assumptions about time difference between Melbourne and Singapore and UTC

Licensed under the terms of the Apache License, Version 2.0 (Murray Andrews 2013)


positional arguments:
  outfile               Output file. If -f not specified then use suffix to
                        select format.

optional arguments:
  -h, --help            show this help message and exit
  -a AGE, --age AGE     Maximum message age (default 24h).
  -c COUNT, --count COUNT
                        Maximum number of messages to dump.
  -f {txt,raw,csv}, --format {txt,raw,csv}
                        Output file format. If not specified then derive from
                        outfile or use txt. If raw then just dump the full
                        record in JSON without analysis.
  -n, --noheader        Don't print a header.
  -o {expiry,stored}, --order {expiry,stored}
                        Message sort key
  -s {redc,mnet,smsg,wtxt}, --source {redc,mnet,smsg,wtxt}
                        Message source. Can be specified multiple times.
"""

__author__ = 'ma'

import sys
import json
import re
import datetime
import urllib
import urllib2
import argparse
from os.path import basename, splitext
import csv

PROG = basename(sys.argv[0])

DESTINATIONS = {
    'XXmnet': '61427842563',
    'mnet': '0408287143',
    'smsg': '61408287143',
    'redc': '61421261189',
    'wtxt': '6596973770'
}

FIELD_NAMES = ['provider', 'dst', 'otp', 't_sent', 't_expiry', 't_stored', 'd_transmit', 'd_timetolive']

OTP_EXPIRY_REGEX = r'.*use it by\s+(?P<expiry>.*?)\s+Singapore'
otp_time_re = re.compile(OTP_EXPIRY_REGEX)

OTP_REGEX = r'The SMS-OTP for your transaction is (?P<otp>\d{6})\.'
otp_re = re.compile(OTP_REGEX)

DUMP_URL = "https://message-grabber-180.appspot.com/dump"
#DUMP_URL = "http://localhost:8080/dump"

time_delta = {
    'otp_life': datetime.timedelta(seconds=100),  # OTPs valid for 100 seconds
    'Singapore': datetime.timedelta(hours=8)
}

time_fmt = {
    'msg': '%H:%M:%S %d/%m/%Y',  # e.g. '17:17:28 01/10/2013'
    'stored': '%Y-%m-%d %H:%M:%S.%f'  # e.g. '2013-10-01 09:56:40.163790'
}


#-------------------------------------------------------------------------------
#-------------------------------------------------------------------------------
class Formatter(object):
    """
    Abstract superclass for all formatters. Sub-classes must have a name of the form
    "Fmttype" (e.g. Fmtcsv) to be automatically detected.
    """

    #-----------------------------------------------------------
    def __init__(self, field_names, outfile=None, header=False, file_mode='w'):
        """
        Open the specified file and prepare it to receive records. All records must
        have the same structure containing the fields specified in field_names.

        :param field_names: A list containing the names of the fields in the order
                            in which they will be written for each record.
        :param outfile:     Name of output file. If None then use stdout.
        :param header:      If True write a header row first. Default False.

        :raises ValueError: If field_names is not an non-empty list.
        :raises IOError:    If output file cannot be opened.
        """

        if not field_names or not isinstance(field_names, list):
            raise ValueError('Missing or malformed field_names argument for formatter')

        self.field_names = field_names

        if outfile:
            self.fp = open(outfile, mode=file_mode)
        else:
            self.fp = sys.stdout

        # Write the header
        if header:
            self.writerow(dict(zip(field_names, field_names)))

    #-----------------------------------------------------------
    def writerow(self, row_data):
        """
        Write a row of data in the appropriate format

        :param row_data:    A dictionary containing the data to write
        """
        raise NotImplementedError('Abstract method writerow must be overridden')

    #-----------------------------------------------------------
    def close(self):
        """
        Finalise and close the output
        """

        if self.fp is not sys.stdout:
            self.fp.close()


#-------------------------------------------------------------------------------
class Fmttxt(Formatter):
    """
    Format rows as tab separated fields.
    """

    #-----------------------------------------------------------
    def __init__(self, field_names, **kwargs):
        """
        See Formatter.__init__()
        """

        self.fmt_s = '\t'.join(["{" + arg + "}" for arg in field_names])
        super(Fmttxt, self).__init__(field_names, **kwargs)

    #-----------------------------------------------------------
    def writerow(self, row_data):
        """
        Write a row of data as tab separated fields.

        :param row_data:
        """

        self.fp.write(self.fmt_s.format(**row_data) + '\n')


#-------------------------------------------------------------------------------
class Fmtcsv(Formatter):
    """
    Format rows as CSV.
    """

    #-----------------------------------------------------------
    def __init__(self, field_names, file_mode='w', **kwargs):
        """
        Setup output in CSV format.

        :param field_names:     See Formatter()
        :param kwargs:          See Formatter()
        """

        # Can't let the superclass __init__ write the header row. We'll handle it here.
        hdr = kwargs.get('header', False)
        kwargs['header'] = False

        file_mode = kwargs.get(file_mode, 'w')[0] + 'b'     # CSV needs binary mode
        super(Fmtcsv, self).__init__(field_names, file_mode=file_mode, **kwargs)
        self.writer = csv.DictWriter(self.fp, fieldnames=field_names, extrasaction='ignore')

        if hdr:
            self.writer.writeheader()

    #-----------------------------------------------------------
    def writerow(self, row_data):
        """
        Write a row of data as CSV.

        :param row_data:        See Formatter()
        """

        self.writer.writerow(row_data)


#-------------------------------------------------------------------------------
class Fmtraw(Formatter):
    """
    Format rows as raw JSON. No analysis done. No header
    """

    #-----------------------------------------------------------
    def __init__(self, field_names, **kwargs):
        """
        Open the output file.

        :param field_names:     Ignore for raw output
        :param kwargs:          Ignored for raw output with possible except of
                                filemode.
        """

        kwargs['header'] = False    # Prevent header row
        super(Fmtraw, self).__init__(field_names, **kwargs)

    #-----------------------------------------------------------
    def writerow(self, row_data):
        """
        Write data as raw JSON.

        :param row_data:        Dictionary of data for the row.
        """

        self.fp.write(json.dumps(row_data) + '\n')


#-------------------------------------------------------------------------------
#-------------------------------------------------------------------------------
def round_time(t):
    """
    Round time to nearest second.

    :param t:       A datetime.datetime object.
    :return:        Rounded datatime.datetime object.
    """

    if t.microsecond >= 500000:
        t += datetime.timedelta(microseconds=1000000 - t.microsecond)
    else:
        t -= datetime.timedelta(microseconds=t.microsecond)

    return t


#-------------------------------------------------------------------------------
def dumper(dst, age='24h', count=1000, orderby='expiry'):
    """
    Generator that dumps records from the GAE database.

    :param dst:         Destination phone number.
    :param age:         Maximum age of dumped records. Default "24h" (24 hours)
    :param count:       Maximum number of records to dump. Default 1000.
    :param orderby:     If 'expiry', records are ordered by expiry time of the OTP.
                        If 'stored', records are ordered by storage time.
                        Default is 'expiry'.

    :return:            A generator.
    """

    dump_params = {
        'dst': dst,
        'fmt': 'json',
        'age': age,
        'orderby': orderby,
        'count': count
    }

    url = DUMP_URL + "?" + urllib.urlencode(dump_params)
    #print >> sys.stderr, "*****", url
    request = urllib2.Request(url)
    response = urllib2.urlopen(request)
    for record in response:
        yield record
    response.close()


#-------------------------------------------------------------------------------
def analyse_rec(record):
    """
    Analyse the timing elements of the record and augment the dictionary with the
    key times in a standard format. We only look at the message expiry time which
    is in Singapore time and the store time in GAE which is in UTC. All times are
    converted back to UTC. Time fields in the output all start with t_ (they are
    datetime objects) and delay fields start with d_ (all ints).

    :param record:      A record (dict) dumped from the GAE database.

    :return:            Nothing. The inbound record just has more fields added.
    """

    msg = str(record['msg'])

    #----------------------------------------
    # Extract the OTP - useful as a almost unique key
    otp = otp_re.search(msg).group('otp')
    record['otp'] = otp

    #----------------------------------------
    # Extract the expiry time on the OTP from the msg string
    # From this we estimate OTP issue time

    expiry_s = otp_time_re.search(msg).group('expiry')

    expiry_time = datetime.datetime.strptime(expiry_s, time_fmt['msg'])

    # Convert Singapore back to UTC - very clunky.
    expiry_time -= time_delta['Singapore']
    record['t_expiry'] = expiry_time
    record['t_sent'] = expiry_time - time_delta['otp_life']

    #----------------------------------------
    # Get the time it was stored by GAE
    stored_s = record['stored']
    record['t_stored'] = round_time(datetime.datetime.strptime(stored_s, time_fmt['stored']))

    #----------------------------------------
    # Calculate delays

    transmit_delay = record['t_stored'] - record['t_sent']
    record['d_transmit'] = transmit_delay.total_seconds()

    time_to_live = record['t_expiry'] - record['t_stored']
    record['d_timetolive'] = time_to_live.total_seconds()


#-------------------------------------------------------------------------------
def main():
    """
    Main.
    """

    #---------------------------------------
    # Get list of supported output formats. Based on existance of Fmt* sub-classes of Formatter

    formats = {x[len('Fmt'):] for x in globals() if x.startswith('Fmt') and issubclass(globals()[x], Formatter)}

    #---------------------------------------
    # Parse options
    argp = argparse.ArgumentParser(description='Dump ACS OTP messages from GAE, optionally analysing transit times.',
                                   prog=PROG)
    argp.add_argument('-a', '--age', default='24h',
                      help='Maximum message age (default 24h).')
    argp.add_argument('-c', '--count', type=int, default=1000,
                      help='Maximum number of messages to dump.')
    argp.add_argument('-f', '--format', choices=formats,
                      help='''Output file format. If not specified then derive from outfile or use txt.
                      If raw then just dump the full record in JSON without analysis.''')
    argp.add_argument('-n', '--noheader', action='store_true', default=False,
                      help="Don't print a header.")
    argp.add_argument('-o', '--order', required=False, choices=('expiry', 'stored'), default='expiry',
                      help='Message sort key')
    argp.add_argument('-s', '--source', required=True, choices=DESTINATIONS, action='append',
                      help='Message source. Can be specified multiple times.')
    argp.add_argument('outfile', nargs='?',
                      help='Output file. If -f not specified then use suffix to select format.')

    args = argp.parse_args()

    #---------------------------------------
    # Determine output format and get the formatter
    fmt = None
    if args.format:
        fmt = args.format
    elif args.outfile:
        # Get file suffix to determine format
        root, sfx = splitext(args.outfile)
        sfx = sfx[1:].lower()

        if sfx in formats:
            fmt = sfx

    if not fmt:
        fmt = 'txt'

    formatter_class = globals()['Fmt' + fmt]
    formatter = None
    try:
        # Instantiate a formatter object from the selected class.
        formatter = formatter_class(FIELD_NAMES, outfile=args.outfile, header=not args.noheader)
    except IOError as e:
        print >> sys.stderr, '{}: {}'.format(PROG, e)
        exit(1)

    #---------------------------------------
    # Loop through all of the required sources
    for destname in args.source:
        #print destname

        if destname not in DESTINATIONS:
            # Shouldn't happen - argparse should block before here
            print >> sys.stderr, "Bad destination: {}".format(destname)
            continue

        dd = dumper(DESTINATIONS[destname], age=args.age, count=args.count, orderby=args.order)

        for r in dd:
            record = json.loads(r)
            if fmt != 'raw':
                analyse_rec(record)
            formatter.writerow(record)

    formatter.close()


if __name__ == '__main__':
    main()
    exit(0)
