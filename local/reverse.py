#!/usr/bin/env python

"""
Print the lines of a file in reverse order. Copies stdin to stdout.
"""

import sys

lines = []
for line in sys.stdin:
    lines.append(line.strip('\n'))

for line in lines[::-1]:
    print line
