[TOC]

-----
# Purpose #

Message Grabber is a REMASYS application that runs on Google App Engine (GAE) to collect and store SMS messages from inbound SMS gateway providers and then make these messages available to EAGLE-i jobs via a HTTP interface.

-----
# Overview #

## Architecture ##

The high level architecture is shown below. Only MessageNet and SMS Global are shown as examples. Other providers interface in the same way although with provider specific URL parameters (see below for individual server provider API specifications).

![message-grabber.png](https://bitbucket.org/repo/9y8jkj/images/2296555978-message-grabber.png)

## Message Flow ##

Message flow for an inbound SMS is:

1.	An SMS is sent to one of our registered virtual numbers and is received by the inbound gateway provider.
2.	The gateway provider issues a HTTP POST or GET to a URL provided by REMASYS for Message Grabber. The SMS details (source, message text etc.) are encoded as parameters in the URL (GET) or message body (POST).
3.	Message Grabber is activated by the incoming HTTP request and performs validation of source IP address and parameter contents using data in config.yaml (refer to section 3.1).
If the message passes validation, then it is stored in the GAE high replication data-store (DB). If the message does not pass validation, then it is discarded.
The parameters vary between providers and need to be mapped to a common set for storage in the database. This mapping is specified in config.yaml.
4.	Sometime later, another entity (typically a DCW), retrieves the message with a HTTP GET to request messages that arrived for a particular inbound virtual number.

The routing of requests, load balancing, dynamic starting and stopping of Message Grabber instances, log management, database replication etc. are all handled automatically by GAE and do not require management by REMASYS.

## Datastore ##

Incoming SMS messages are stored in the GAE high replication database (DB). The schema is described below.

```
#!text
Note: Message Grabber uses the older db datastore rather than the current (preferred) ndb. This is not a problem.
```
|Field Name|Description|
|-|-|
|ID|Record key assigned by GAE.|
|ip|Source IP address for the request.|
|provider|A string indicating the SMS service provider that delivered the message.|
|src|Source number from which the SMS originated. May be alphanumeric as some SMS blast services use textual source identifiers.|
|dst|Destination number to which the SMS was sent. This will be one of the inbound virtual numbers assigned by an SMS gateway provider.|
|msg|The message text.|
|recv|An optional message receipt time provided by the SMS gateway provider. In most cases it is very unclear what this means. When it is provided, Message Grabber does nothing with it other than store it in the data base. It should not be relied on for any purpose other than as a hint in a debugging exercise.|
|sent|An optional message sent time provided by the SMS gateway provider. In most cases it is very unclear what this means. When it is provided, Message Grabber does nothing with it other than store it in the data base. It should not be relied on for any purpose other than as a hint in a debugging exercise.|
|stored|The UTC date and time at which the record was stored in the GAE data base. The /out and /dump resources can sort on this field.|
|expiry|Specific to ANZ ACS. This is the expiry time for the One Time Password (OTP) extracted as a text string from the text message. The /out and /dump resources can sort on this field.|

-----
#  Message Grabber Interface #
Message Grabber is accessed at the following URL:

```
#!http
https://message-grabber-180.appspot.com
```

Unrecognised request parameters are silently ignored.

Missing mandatory parameters or those that fail validation will result in a Warning or Error message in the GAE logs.

For `POST` requests, the parameters are URL encoded in the request body. 

For `GET` requests, the parameters are URL encoded in the request URL.

All connections should be via HTTPS. Attempts to connect via HTTP will be redirected to HTTPS.

Access to Message Grabber is not authenticated. Access to each of the URLs can be controlled based on source IP address. The configuration file ```config.yaml``` specifies permitted source IP addresses for HTTP requests. Requests from other addresses will result in Error 403 – Forbidden. A list of allowed IP addresses can be specified for each resource, including IP4 and IP6 addresses and CIDR formatted ranges for IP4 or IP6.

## Receive inbound SMS ##

Receive inbound SMS messages from a provider. 

```
#!make

Method(s): GET or POST depending on the SMS provider API requirements
Path: /in*
```

### Request ###

The actual resource name always starts with “/in” but the full name is unique for each gateway provider and is configured in ```config.yaml```.

Request parameters and HTTP methods differ for each SMS gateway provider. The API for each provider is configured in ```config.yaml```.

### Response ###

SMS provider dependent. Typically HTTP 200 but they do vary.

## Retrieve Stored Messages ##

Retrieve stored SMS messages from the GAE datastore.
```
#!make

Method: GET
Path: /out
```

### Request ###

|Parameter|Description|
|-|-|
|dst|Destination number. This will be an inbound virtual number assigned by an SMS gateway provider. Mandatory.|
|count|Maximum number of messages to return. Must be ≤ 10. Optional. Default: 1|
|age|Maximum age of messages based on stored time. Formatted as `^\d+[wdhms]?$`. e.g. `24h` = 24 hours, `10m` = 10 minutes. Optional. Default: no limit.|
|fmt|Output format. Must be either `json` or `xml`. Optional. Default `json`.|
|orderby|Field to use as the sort key. Either `stored` or `expiry`. Optional. Default: `expiry`.|


### Response ###

A list of messages. The output format can be JSON or XML depending on the `fmt` parameter in the request.

Each record contains all fields specified in the Message Grabber Data Schema above except for `ID`.

Messages are produced in reverse time order (i.e. most recent first).

## Dump messages ##

Dump a number of messages from the datastore. Typically used for debugging. 

```
#!make

Method: GET
Path: /dump
```

### Request ###

|Parameter|Description|
|-|-|
|dst|Destination number. This will be an inbound virtual number assigned by an SMS gateway provider. Mandatory.|
|count|Maximum number of messages to return. Must be ≤ 5000. Optional. Default: 1000.|
|fmt|Output format. Must be either `json` or `xml`. Optional. Default `json`.|
|orderby|Field to use as the sort key. Either `stored` or `expiry`. Optional. Default: `expiry`.|

### Response ###

A list of messages. The output format can be JSON or XML depending on the `fmt` parameter in the request.

Messages are produced in reverse time order (i.e. most recent first).

## Purge old messages ##

Purge old entries from the GAE datastore. This is typically run by the cron service on GAE.

Access to his resource must either come from GAE itself (i.e. cron) or from an authenticated administrator.

```
#!make

Method: GET (yes I know - should be DELETE but urllib2 doesn't handle it).
Path: /purge
```
### Request ###

This is a deferred (asynchronous) operation. The request just initiates the process.

|Parameter|Description|
|-|-|
|age|Delete messages older than this, based on stored time. Formatted as `^\d+[wdhms]?$`. e.g. `24h` = 24 hours, `10m` = 10 minutes. Optional. Default: ‘48h’.|

```
#!text
Note: cron.yaml currently overrides the default to 3d.
```

### Response ###

Status only. The status only indicates that the request was accepted - not whether it worked. Check the logs for that.

If the purge takes too long it will be aborted by GAE. This is not a problem - it will pick up where it left off on the next run.

-----
# Configuration #

The Message Grabber application consists of:

* A few Python files (*.py)

* A few configuration files (*.yaml)
    * config.yaml: This is the main application configuration file. It determines what SMS gateways are implemented, how to map their APIs to the datastore and what source IP addresses can access what resources.
    * cron.yaml: Controls how often GAE cron jobs run. The only one configured for Message Grabber is a periodic purge of old messages. This should not need to be changed often.
    * index.yaml: Don’t touch it. This file is automatically generated by the GAE development kit.
    * app.yaml: When a new version of the application or config.yaml needs to be uploaded,  update the application version number in this file. See [Application Version Control](#markdown-header-application-version-control).

Any configuration change requires the code to be uploaded to GAE via the Google App Engine Launcher or the command-line equivalent (appcfg.py). Only changed files will be uploaded.

## API Configuration ##

The interface provided by Message Grabber is almost totally controlled from config.yaml, which contains extensive comments explaining the format. Important keys are:

* **logging:** Controls logging level and whether log messages generate email messages.
* **handlers:** Defines the parameters accepted by all of the API resources and the IP addresses that are allowed to access them. There is one sub-key for each available resource. Inbound message handlers all start with `in`. 

## Access Control Configuration ##

Access to resources provided by Message Grabber, as listed in Table 2 above, is controlled by source IP addresses specified under the ‘handlers’ key in `config.yaml`.

An update to `config.yaml` will usually be required if an SMS gateway provider switches to a new IP address or we add new EUE streams with different IP addresses.

Each handler specified under the `handlers` key in `config.yaml` has an `allowed_IPs` key which can contain a single address or a list of allowed addresses. Nested lists are permitted. Addresses can be IP4, IP6 or CIDR formatted ranges for either address family.

If the `allowed_IPs` key is missing or empty then there are no access restrictions.

If all access should be blocked, then use `0.0.0.0` (or `*ip_none`) as the only element in the list for the `allowed_IPs` key.

Access attempts from unauthorised addresses will produce an Error level message in the GAE log.

## Cron Configuration

GAE runs a regular cron job against Message Grabber to delete old messages by accessing the `/purge` resource. This is configured in `cron.yaml` and should not need to be changed.

## Checking Configuration ##

:ambulance: If `config.yaml` is malformed then Message Grabber will fail horribly.

A basic checking utility is provided in `local/checkconf.py`. This will verify syntax and also check some, but not all, aspects of the expected contents. Usage is:

```
#!bash
python local/checkconf.py config.yaml
```

## Application Version Control ##

### Version Numbers ###

GAE applies a version number to each application. This is user defined as the `version` key in `app.yaml`.

The version string is almost free-form but cannot contain ‘.’. For Message Grabber we use the form:

* major-minor (e.g. 1-1); or
* major-minor-config (e.g. 1-1-2).

The major-minor combination refers to code or functional changes. The `-config` format should be used when `config.yaml` is modified but there is no code change.

## Uploading New Versions ##

When a new version needs to be deployed use the following process:

1. Use `local/checkconf.py` to do a health check on `config.yaml`.
2. Update the version key in `app.yaml`.
3. Use `appcfg.py` or the Google App Engine Launcher to upload the new code.
    This is safe to do as the new version will not be serving live traffic until it is activated.
4. Login to the GAE console, select the ```message-grabber-180``` application and go to the _Versions_ page. The previous version should be shown as the ‘default’ which is handling live traffic. The newly uploaded version should be visible but will not be serving live traffic.
5. Activate the new version by making it the default. This will make the new version active and the previous version dormant. **Do not** delete the previous version.
6. Check the logs and database to make sure it is operating correctly.
7. If a rollback is required, return to the _Versions_ page and switch the default back to the previous version.

##  GAE Administration ##

The GAE console is available at:

```
#!make
URL: https://appengine.google.com
Login account: remasysacssms@gmail.com
```

Key components of interest are:

* Dashboard: Overview of resource usage
* Instances: Shows how many instances of Message Grabber are running. These are started on demand automatically by GAE. Typically 0, 1 or 2 instances will be running.
* Logs: Every access attempt is logged with the full access URL. Be sure to select the application version of interest.
* Versions: Allows activation and deactivation of specific versions.
* Quota Details: Shows resource usage. This resets on a daily basis. Message Grabber should generally run entirely in the GAE free tier. However, on occasion it may exceed this limit. To avoid blocking, a billing arrangement has been established to allow the application to run in paid mode. This will happen automatically when a free quota limit is reached.
* Datastore Viewer: View database entries.

When using the datastore view, by default, sort order of displayed records is random. To see the recent messages, open the _Options_ drop-down and enter:
```
#!sql
SELECT * FROM TxtMsg ORDER BY expiry DESC
```

or

```
#!sql
SELECT * FROM TxtMsg ORDER BY stored DESC
```

## Dump Interface ##

Message Grabber supports a `dump` interface which is useful for extracting a large number of records for debugging purposes. The appropriate URL can be constructed manually and used with a browser or curl/wget to extract data.

Alternatively use `local/dumper.py` to extract data, convert times to a Melbourne base and write the output in text or CSV format. Usage is:

```
#!bash
python dumper.py [-h | --help ] [options…]
```

For convenience, there is a `getem.bat` command file which extracts the last 24 hours of data from all three of the current providers (Worldtext, MessageNet and SMS Global) and creates a CSV file for each. Just run the script without arguments and 3 *.csv files will be created (providing Python is installed).

# SMS Providers #

See `config.yaml` for details on SMS provider APIs, IP addresses etc.

## MessageNet ##

| | |
|-|-|
|Website|www.messagenet.com.au|
|Contact Number|1300 551 515|
|Support Email|support@messagenet.com.au|
|Virtual Number|61427842563 (Telstra)|
|Message Grabber Resource|/in|

## SMS Global ##

| | |
|-|-|
|Website|www.smsglobal.com|
|Contact Number|1300 883 400|
|Support Email|support@smsglobal.com|
|Virtual Number|61408287143 (Telstra)|
|Message Grabber Resource|/in-sg|

## WorldText ##

WorldText are UK based but have been able to provide an inbound number in Singapore.

| | |
|-|-|
|Website|www.world-text.com|
|Contact Number|+44 845 867 3980|
|Support Email|support@world-text.com|
|Virtual Number|+6596973770|
|Message Grabber Resource|/in-wt|

## Twilio ##

Twilio are US based.

Twilio do not have fixed sending IP addresses so Message Grabber cannot filter on them. There is a password parameter in Twilio requests to provide some control. See `config.yaml`

| | |
|-|-|
|Website|www.world-text.com|
|Contact Number|?|
|Support Email|See website|
|REMASYS account login|support@remasys.com|
|Virtual Number|+1 928-358-5321|
|Message Grabber Resource|/in-twilio|

# Version History #

## 1-5-4 ##

Added new MessageNet IP addresses.