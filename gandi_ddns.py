import configparser as configparser
import sys
import time
import os
import requests
import json
import ipaddress
import socket
from datetime import datetime
import msg

config_file = "config.txt"

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))

def get_ip(m,ipservice,protocol):
    # I've spent some time changing back and forth between ifconfig.co
    # and ipify.org, as their IPv6 support has gone back and forth
    # and changed in the way one accesses it.  I'm actually leaving
    # the code for both in now, and allowing selection in the config.

    if ipservice == "ipify.org":
        # ipify.org currently (2021-08-02) allows selection of which
        # protocol via the service name, so the requests package
        # can be used, which means this script can work on Windows.

        serv = "http://api%s.ipify.org/" % protocol
        ip = requests.get(serv).text
    elif ipservice == "ifconfig.co":
        # ifconfig.co used to allow v4 and v6 subdomains to force
        # protocols, but as of 2018-07-25 it no longer does.
        # forcing requests.get to use a particular protocol is
        # upleasant (must fiddle with underlying socket) so
        # we run curl in a popen.  This unfortunately means the 
        # script won't run on Windows.

        serv = 'curl -s%s http://ifconfig.co/' % protocol

        p = os.popen(curlcmd)
        ip = p.read().rstrip()
        rc = p.close()
        if rc:
           m.put(msg.ERROR,'Return code %d from %s' % (rc, serv))
        sys.exit(2)
        if ip == "":
            m.put(msg.ERROR,
                  'Did not get ip from %s despite rc=%d' % (serv,rc))
    else:
        m.put(msg.ERROR, 'Unknown ipservice %s' % ipservice)

    try:
        if protocol == '4':
            if not(ipaddress.IPv4Address(ip)): # check if valid IPv4 address
                m.put(msg.ERROR,'Bogus response %s from %s' % (ip, serv))
                sys.exit(2)

        if protocol == '6':
            if not(ipaddress.IPv6Address(ip)): # check if valid IPv6 address
                m.put(msg.ERROR,'Bogus response %s from %s' % (ip, serv))
                sys.exit(2)
    except Exception:
        m.put(msg.ERROR,'%s failed somehow' % serv)
        sys.exit(2)
    return ip

def read_config(config_path):
    # Read configuration file
    cfg = configparser.ConfigParser()
    cfg.read(config_path)
    return cfg

def apply_config_defaults(sec):
    if not sec.get('ipservice'):
        sec['ipservice'] = ipify.org
    fqdn = socket.getfqdn().split('.',1)
    if not sec.get('domain'):
        if len(fqdn) != 2:
            m.put(msg.ERROR,'System host name not qualified, fix system config or supply domain in config.txt')
            sys.exit(2)
        sec['domain'] = fqdn[1]
    if not sec.get('a_name'):
        if len(fqdn) < 1:
            m.put(msg.ERROR,'System host name not configured, fix system config or supply a_name in config.txt')
            sys.exit(2)
        sec['a_name'] = fqdn[0]
    if not sec.get('aaaa_name'):
        sec['aaaa_name'] = sec.get('a_name')
    if not sec.get('protocols'):
        sec['protocols'] = '4'
    if sec['protocols'] not in ['4', '6', '46', '64', 'none']:
        m.put(msg.ERROR,'Invalid protocols value \"%s\", fix config.txt' % (
            sec['protocols']))
        sys.exit(2)
    if sec['protocols'] == 'none':
        sec['protocols'] = ''
    if not sec.get('ttl'):
        sec['ttl'] = '900'
    if not sec.get('api'):
       sec['api'] = 'https://dns.api.gandi.net/api/v5/'

def hdrs(cfg):
    #Set headers
    return { 'Content-Type': 'application/json',
             'X-Api-Key': '%s' % cfg['apikey']}



def get_record(m, cfg):
    # Get existing record
    r = requests.get(cfg['url'], headers=hdrs(cfg))
    return r

def update_record(m, cfg, external_ip):
    # Prepare record
    payload = {'rrset_ttl':    cfg['ttl'],
               'rrset_values': [external_ip]}
    # Add record
    r = requests.put(cfg['url'], headers=hdrs(cfg), json=payload)

    if r.status_code == 201:
        m.put(msg.INFO,'Zone %s %s/%s record updated.' % (
            cfg['domain'], cfg['recordname'], cfg['recordtype']))
    else:
        m.put(msg.ERROR,'Record update failed with status code: %d' %
                r.status_code)
        m.put(msg.ERROR,(r.text))
    return r


def main():
    # actually don't know if script could work on Python earlier
    # than 3.5.x, but that's the earliest I tested with
    assert sys.version_info >= (3,5)


    path = config_file
    if not path.startswith('/'):
        path = os.path.join(SCRIPT_DIR, path)
    config = read_config(path)
    if not config:
        sys.exit("Please fill in the 'config.txt' file.")

    for section in config.sections():
        # don't iterate over config, that will process the DEFAULT section
        sec = config[section]
        apply_config_defaults(sec)
        m = msg.Msg();
        m.setlevel(sec['verbosity'])
        for protocol in sec['protocols']:
            m.put(msg.INFO,'%s - section %s - IPv%s' % (
                   str(datetime.now()),
                   section,
                   protocol))

            # deduce DNS record type
            sec['recordtype'] = {'4': 'A', '6': 'AAAA'}[protocol]
            # deduce DNS record name
            sec['recordname'] = {'4': sec['a_name'],
                                 '6': sec['aaaa_name']}[protocol]



            # Set URL. It ends up looking like:
            # https://dns.api.gandi.net/api/v5/domains/example.com/raspian/A
            sec['url'] = '%sdomains/%s/records/%s/%s' % (
                sec['api'],
                sec['domain'],
                sec['recordname'],
                sec['recordtype'])
            m.put(msg.INFO,'Request API URL is: %s' % sec['url'])

            # Recently I started getting occasional 502 ("Bad Gateway")
            # errors.  Interestingly, this only happens when I run
            # the script from a cron job, and only at the run
            # at the top of the hour (hh:00),  The runs at
            # hh:20 and hh:40 never fail and another system whic runs
            # hourly at hh:07 never fails.  My guess is that there are
            # a lot of people running some form of dns update from
            # cron, with a run at the top of the hour, resulting in
            # server overload (kind of a unintentional DDOS.)

            # To combat this, if a 502 error is received, wait a little
            # and retry, but give up if the error persists.  I'm also
            # going to change my cron job to move off the top of the hour.
            
            # Check current record

            max_retries = 5
            retry_delay = 23

            for attempt in range(max_retries):
                record = get_record(m,sec)
                if record.status_code != 502:
                    break
                m.put(msg.ERROR,
                      'Got error %d fetching %s record. Retry %d.' %
                      (record.status_code,
                       sec['recordtype'],
                       attempt))
                time.sleep(retry_delay)

            if record.status_code == 502:
                m.put(msg.ERROR,
                      'Got error %d repeatedly fetching %s record. Giving up.' %
                      (record.status_code,
                       sec['recordtype']))
                sys.exit(2);

            if record.status_code == 404:
                # no old record, add it
                # Discover External IP
                external_ip = get_ip(m,sec['ipservice'],protocol)
                m.put(msg.ACTION,'No old %s record, adding as %s' % (
                        sec['recordtype'],
                        external_ip))

                update_record(m,sec, external_ip)
            elif record.status_code == 200:
                # old record exists, check and replace if needed
                old_ip = json.loads(record.text)['rrset_values'][0]
                m.put(msg.INFO,'Current %s record value is: %s' % (
                    sec['recordtype'],
                    old_ip))

                # this is a very particular quirk for my own home config.
                # if there is a nonroutable IP address in an A record,
                # I have put it there for convenience in using one host on
                # my home network from another, do not update it with
                # the external IP.  This path should never be executed
                # if I've configured the script right on my own systems,
                # since the systems where <hostname>.my.domain/A is set to
                # an unroutable IP should be configured to only update
                # the AAAA records, and I doubt anybody else is crazy
                # enough to put private IPs in DNS (I actually don't
                # even do it any more since I now depend on mDNS
                # for local name resolution, which is much saner.)

                if (protocol == '4' and
                    ipaddress.IPv4Address(old_ip).is_private):
                    m.put(msg.ERROR,
                            'Not updating %s record for %s, check config' % (
                                names[protocol],
                                old_ip))
                    continue # next protlocol


                # Discover External IP
                external_ip = get_ip(m,sec['ipservice'],protocol)
                m.put(msg.INFO,'External IP is: %s' % external_ip)

                if old_ip == external_ip:
                    m.put(msg.NOACTION,
                          'No change in IPv%s address, nothing done.' % (
                              protocol))
                else:
                    m.put(msg.ACTION,'Updating %s/%s from %s to %s' % (
                        sec['recordname'],
                        sec['recordtype'],
                        old_ip,
                        external_ip))
                    update_record(m, sec, external_ip)
            else:
                # some unexpected condition fetching old record.
                # perhaps config is bad or api has changed?
                m.put(msg.ERROR,'Got error %d fetching %s record. Stop.' %
                      (record.status_code,
                       sec['recordtype']))
                sys.exit(2)
                
                
            continue # next protocol
        continue # next config secion


if __name__ == "__main__":
    main()
