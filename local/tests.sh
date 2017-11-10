##/bin/sh

local="http://localhost:9080"
#google="https://message-grabber-180.appspot.com"

site="$local"
now=`date +%F:%X`
epoch=`date +%s`

msg='Please+use+it+by+17%3A27%3A20+11%2F10%2F2013++Singapore+Time.'

echo $args
for arg in $@
do
	url= "$local"
	case "$arg"
	in
	loc*)
		site="$local"
		;;
	goo*)
		site="$google"
		;;
	"in")
		# MessageNet format input
		args="in/?phone=ANZ&dedicated=61427842563&msg=$msg&date_sent=before&date_received=$now"
		;;
	in-d*)
		# MessageNet format input with Debug
		args="in/?phone=ANZ&dedicated=61427842563&msg=$msg&date_sent=before&date_received=$now&debug"
		;;
	ing)
		# SMS Global format input
		args="in-sg/?from=ANZ&to=61408287143&msg=$msg&date=$now"
		;;
	ing-d*)
		# SMS Global format input with debug
		args="in-sg/?from=ANZ&to=61408287143&msg=$msg&date=$now&debug"
		;;

	out)
		# Retrieve most recent MessageNet entry less than 10 mins old
		args="out/?dst=61427842563&age=10m&fmt=json"
		;;
	outg)
		# Retrieve most recent SMSglobal entry less than 10 mins old
		args="out/?dst=61408287143&age=10m&fmt=json"
		;;
	purge)
		args="purge/?age=0"
		;;
	*)
		echo Unknown test $arg - abort
		exit 1
	esac
	#[ "$args" != "" ] && 
     #curl '$site/$args'
	sleep 1
done
