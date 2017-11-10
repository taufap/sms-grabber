#!/bin/sh

age=24h
format=csv
PROVIDERS="mnet smsg wtxt"

args=`getopt a:f: $*`

if [ $? -ne 0 ]
then
	echo "Get message history from message grabber" >&2
	echo "Usage: $0 [-a age] [-f format]" >&2
	echo "Default age is $age. Default format is csv - can be raw (JSON) or txt or csv" >&2
	exit 2
fi

set -- $args

for i
do
	case "$i"
	in
		-a)
			age="$2"
			shift 2
			;;
		-f)
		    format="$2"
		    [ "$format" == "json" ] && format=raw
		    shift 2
		    ;;
		--)
			shift
			break
			;;
	esac
done


for provider in $PROVIDERS
do
	echo "$provider ... "\\c
	python dumper.py -s$provider -a$age $provider.$format && echo Created $provider.$format
done
