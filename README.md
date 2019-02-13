Python script to update DNS A and/or AAAA record of your domain dynamically using gandi.net LiveDNS API:

http://doc.livedns.gandi.net/

The script was developed for those behind a dynamic IP interface (e.g. home server/pi/nas).

Forked by Rich McAllister (k6rfm) to supporting ipv6 (setting AAAA records.) This required changing to ifconfig.co as the IP service

The config-template.txt file should be renamed to config.txt, and modified with your gandi.net API key, domain name, and A-record (@, dev, home, pi, etc).

Every time the script runs, it will query an external service to retrieve the external IP of the machine, compare it to the current record in the zone at gandi.net, and then update the record if the IP has changed.

Requirements:

  use python3 (actually I don't know if there's anything version 3 specific,
  but it's the only version I've tried)

  pip install -r requirements.txt

You can then run the script as a cron job :

```
7,22,37,52 * * * * python3 /home/user/gandi-ddns/gandi_ddns.py
```
or on a systemd/journald system try
```
6,26,46 * * * * systemd-cat -t "ddns" python3 /home/user/gandi-ddns/gandi_ddns.py
```
to route any messages to the journal/syslog, rather than getting those annoying
cron emails.

I recommend setting the cron job to not run exactly at the top of the
hour (hh:00) since I sometimes got temporary failures accessing the
Gandi servers then. I suspect there are a lot of people running DNS
updates at that time, causing server overload.  Pick some more random times,
don't everybody use the ones in my examples.

macOS (not tested by k6rfm, inherited)

```
cd gandi-ddns
ln -s $(pwd) /usr/local/gandi-ddns
sudo cp gandi.ddns.plist /Library/LaunchDaemons/
sudo launchctl /Library/LaunchDaemons/gandi.ddns.plist
```
