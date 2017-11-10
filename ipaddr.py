"""
Muck about with IP addresses. Quick and dirty. There are much better IP address
manipulation modules out there.

Licensed under the terms of the Apache License, Version 2.0 (Murray Andrews 2013)
"""

__author__ = 'ma'

import socket
from binascii import hexlify, unhexlify


IP_LEN = {4: 32, 6: 128}  # Address length in bits for IP4 and IP6


def int_to_ip(ip_n, family=4):
    """
    Convert an integer to a string representation of an IP address.

    :param ip_n:        An integer representing an IP address
    :param family:      An integer representing address family (4 for IP4, 6 for IP6).
                        Default is 4.
    :return:            A string representation of the address in either IP4 dot notation
                        or IP6 colon notation as appropriate.
    :raises:            ValueError if the conversion fails or invalid family specified.
    """

    if family not in IP_LEN:
        raise ValueError('Invalid address family: {}'.format(family))

    addr_family = socket.AF_INET if family == 4 else socket.AF_INET6

    hexdigits = IP_LEN[family] / 4

    try:
        ip = socket.inet_ntop(addr_family, unhexlify('{ip:0{digits}x}'.format(ip=ip_n, digits=hexdigits)))
    except:
        raise ValueError('Cannot convert {} to IP{} address'.format(ip_n, family))

    return ip


#-------------------------------------------------------------------------------
def ip_to_int(ip):
    """
    Convert an IP address to an integer/long. Will attempt to work out whether it is
    an IP4 or IP6 address.

    :param ip:          An IP address specified as a string in the traditional IP4 dot
                        notation (e.g. 192.168.1.1) or IP6 colon notation (e.g. ::1).
    :return:            A tuple (
                            The integer/long equivalent of the IP address,
                            4 or 6 indicating whether it was an IP4 or IP6 address
                        )
    :raises:            ValueError if ip is malformed.

    """

    ip = ip.strip()

    family, addrtype = (socket.AF_INET6, 6) if ':' in ip else (socket.AF_INET, 4)

    try:
        ip_n = int(hexlify(socket.inet_pton(family, ip)), 16)
    except:
        raise ValueError('Invalid IP address: {}'.format(ip))

    return ip_n, addrtype


#-------------------------------------------------------------------------------
def ip_cidr_match(ip, ip_range):
    """
    Match an IP address to a CIDR block/prefix range. Works for IP4 and IP6.

    :param ip:          An IP address specified as a string in the traditional IP4 dot
                        notation (e.g. 192.168.1.1) or IP6 colon notation (e.g. ::1).
    :param ip_range:    A CIDR formatted address range string (block/prefix). IP4 or IP6.
    :return:            True if ip is in ip_range. False otherwise.
    :raises:            ValueError if ip or ip_range are malformed.
    """

    if '/' not in ip_range:
        raise ValueError('IP range not in CIDR format: ' + ip_range)

    ip_n, ip_family = ip_to_int(ip)

    block, prefix = ip_range.strip().split('/')
    block_n, block_family = ip_to_int(block)

    try:
        prefix_n = int(prefix)
    except ValueError:
        raise ValueError('Invalid prefix {} in CIDR: {}'.format(prefix, ip_range))

    if ip_family != block_family:
        # Not same protocol type - can't match
        return False

    ip_len = IP_LEN[block_family]
    if not 0 <= prefix_n <= ip_len:
        raise ValueError('Prefix {} out of range in CIDR: '.format(prefix, ip_range))

    # Have a valid IP address block and prefix. Get the mask.
    full_mask = 2 ** ip_len - 1  # Full length mask for the address family (IP4 or IP6)
    range_size = 2 ** (ip_len - prefix_n)  # Size of range specified by the CIDR prefix length
    range_mask = ~(range_size - 1) & full_mask  # Bit mask to get invariant element of block in ip_range

    range_start = block_n & range_mask
    range_end = range_start + range_size - 1

    return range_start <= ip_n <= range_end


#-------------------------------------------------------------------------------
def ip_match(ip, ip_range):
    """
    Determines if the specified IP address is in the range specified in ip_range.
    Handles IP4 and IP6. Its safe to mix address types however IP4 addresses will
    never match IP6 addresses.

    :param ip:          An IP address specified as a string in the traditional IP4 dot
                        notation (e.g. 192.168.1.1) or IP6 colon notation (e.g. ::1).
    :param ip_range:    An IP address range which can be any of the following:
                            A single IP address (as for parameter ip)
                            A CIDR formatted address range (IP4 or IP6)
                            An iterable of items from above (typically, a list or set or a
                            nested ip_range). The function will return True if ip is in
                            any of the ones in the iterable.
    :return:            True if ip is in ip_range. False otherwise.
    :raises:            ValueError if any of the arguments are malformed.
    """

    if isinstance(ip_range, str):
        # See if we have a CIDR
        if '/' in ip_range:
            return ip_cidr_match(ip, ip_range)
        else:
            # Assume we have single address to compare
            ip_n, ip_family = ip_to_int(ip)
            range_n, range_family = ip_to_int(ip_range)

            return ip_family == range_family and ip_n == range_n
    else:
        # Assume we have an iterable
        for ipr in ip_range:
            if ip_match(ip, ipr):
                # Found a match - bailout with success
                return True

        # No matches
        return False
