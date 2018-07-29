import configparser as configparser
import sys
import os
import requests
import json
import ipaddress
import socket
from datetime import datetime
import msg

config_file = "config.txt"

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))

def get_ip(m,protocol):
    # ifconfig.co is used as api.ipify.org doesn't do ipv6 (the
    # docs say it does, and I suspect the server code would work,
    # but api.ipify.org doesn't have a AAAA record because the underlying
    # web service doesn't do v6)
    # ifconfig.co used to allow v4 and v6 subdomains to force
    # protocols, but as of 2018-07-25 it no longer does.
    # forcing requests.get to use a particular protocol is
    # unpleasant (must fiddle with underlying socket) so
    # we run curl in a popen.
    #  x =
    curlcmd = 'curl -s%s http://ifconfig.co/' % protocol

    #Get external IP
    try:
        ip = os.popen(curlcmd).read().rstrip()
        if protocol == '4':
            if not(ipaddress.IPv4Address(ip)): # check if valid IPv4 address
                m.put(ERROR,'Bogus response %s from %s' % (ip, ip_service))
                sys.exit(2)

        if protocol == '6':
            if not(ipaddress.IPv6Address(ip)): # check if valid IPv6 address
                m.put(ERROR,'Bogus response %s from %s' % (ip, ip_service))
                sys.exit(2)
    except Exception:
        m.put(ERROR,'% failed somehow' % curlcmd)
        sys.exit(2)
    return ip

def read_config(config_path):
    # Read configuration file
    cfg = configparser.ConfigParser()
    cfg.read(config_path)
    return cfg

def apply_config_defaults(sec):
    fqdn = socket.getfqdn().split('.',1)
    if not sec.get('domain'):
        if len(fqdn) != 2:
            m.put(ERROR,'System host name not qualified, fix system config or supply domain in config.txt')
            sys.exit(2)
        sec['domain'] = fqdn[1]
    if not sec.get('a_name'):
        if len(fqdn) < 1:
            m.put(ERROR,'System host name not configured, fix system config or supply a_name in config.txt')
            sys.exit(2)
        sec['a_name'] = fqdn[0]
    if not sec.get('aaaa_name'):
        sec['aaaa_name'] = sec.get('a_name')
    if not sec.get('protocols'):
        sec['protocols'] = '4'
    if sec['protocols'] not in ['4', '6', '46', '64']:
        m.put(ERROR,'Invalid protocols value \"%s\", fix config.txt' % (
            sec['protocols']))
        sys.exit(2)
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


            # Check current record
            record = get_record(m,sec)

            if record.status_code != 200:
                # Discover External IP
                external_ip = get_ip(m,protocol)
                m.put(msg.ACTION,'No old %s record, adding as %s' % (
                        sec['recordtype'],
                        external_ip))

                update_record(m,sec, external_ip)
            else:
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
                # enough to put private IPs in DNS....

                if (protocol == '4' and
                    ipaddress.IPv4Address(old_ip).is_private):
                    m.put(msg.ERROR,
                            'Not updating %s record for %s, check config' % (
                                names[protocol],
                                old_ip))
                    continue # next protocol


                # Discover External IP
                external_ip = get_ip(m,protocol)
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
            continue # next protocol
        continue # next config secion


if __name__ == "__main__":
    main()
