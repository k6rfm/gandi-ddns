import configparser as configparser
import sys
import os
import requests
import json
import ipaddress
import socket
from datetime import datetime

config_file = "config.txt"

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))

def get_ip(protocol):
    # ifconfig.co has separate names for v4 and v6, so we use it.
    # api.ipify.org handles both, but with the same site name,
    # and forcing requiest.get to use a particular protocol is
    # unpleasant (must fiddle with underlying socket.)
    # running a curl command would work since curl has protocol
    # options, but a fork/exec is unesthetic..
    ip_service = 'https://v%s.ifconfig.co/ip' % protocol

    #Get external IP
    try:
        r = requests.get(ip_service, timeout=3)
    except Exception:
        print('Failed to retrieve external IP from ', ipservice)
        sys.exit(2)
    if r.status_code != 200:
        print(('Failed to retrieve external IP. Server responded with status_code: %d' % r.status_code))
        sys.exit(2)

    ip = r.text.rstrip() # strip \n and any trailing whitespace

    if protocol == '4':
        if not(ipaddress.IPv4Address(ip)): # check if valid IPv4 address
            print('Bogus response %s from %s' % (ip, ip_service))
            sys.exit(2)
    if protocol == '6':
        if not(ipaddress.IPv6Address(ip)): # check if valid IPv6 address
            print('Bogus response %s from %s' % (ip, ip_service))
            sys.exit(2)
    return ip

def read_config(config_path):
    # Read configuration file
    cfg = configparser.ConfigParser()
    cfg.read(config_path)
    return cfg

def get_record(url, headers):
    # Get existing record
    r = requests.get(url, headers=headers)
    return r

def update_record(url, headers, config, section, external_ip):
    # Prepare record
    payload = {'rrset_ttl':    config.get(section, 'ttl'),
               'rrset_values': [external_ip]}
    # Add record
    r = requests.put(url, headers=headers, json=payload)
    if r.status_code == 201:
        print('Zone record updated.')
    else:
        print(('Record update failed with status code: %d' % r.status_code))
        print((r.text))
    return r


def main():
    # actually don't know if script could work on Python earlier
    # than 3.5.x, but that's the earliest I tested with
    assert sys.version_info >= (3,5)

    RECORD_TYPE = {'4': 'A', '6': 'AAAA'}

    path = config_file
    if not path.startswith('/'):
        path = os.path.join(SCRIPT_DIR, path)
    config = read_config(path)
    if not config:
        sys.exit("Please fill in the 'config.txt' file.")

    # TODO: apply defaults for unset values, check that protocols is
    # what we need

    for section in config.sections():
        for protocol in config.get(section, 'protocols'):
            print('%s - section %s - IPv%s' % (
                   str(datetime.now()),
                   section,
                   protocol))
            # retrieve names
            names = {'4': config.get(section, 'a_name'),
                     '6': config.get(section, 'aaaa_name')}
            #Retrieve API key
            apikey = config.get(section, 'apikey')

            #Set headers
            headers = { 'Content-Type': 'application/json',
                        'X-Api-Key': '%s' % config.get(section, 'apikey')}

            # Set URL. It ends up looking like:
            # https://dns.api.gandi.net/api/v5/domains/pensfa.org/raspian/A
            url = '%sdomains/%s/records/%s/%s' % (
                config.get(section, 'api'),
                config.get(section, 'domain'),
                names[protocol],
                RECORD_TYPE[protocol])
            print('Request API URL is: %s' % url)


            # Check current record
            record = get_record(url, headers)

            if record.status_code != 200:
                # Discover External IP
                external_ip = get_ip(protocol)
                print('No old %s record, adding as %s' % (
                        RECORD_TYPE[protocol],
                        external_ip))

                update_record(url, headers, config, section, external_ip)
            else:
                old_ip = json.loads(record.text)['rrset_values'][0]
                print('Current %s record value is: %s' % (
                        RECORD_TYPE[protocol],
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
                    print('Not updating %s record for %s, check config' % (
                            names[protocol],
                            old_ip))
                    continue # next protocol


                # Discover External IP
                external_ip = get_ip(protocol)
                print(('External IP is: %s' % external_ip))

                if old_ip == external_ip:
                    print('No change in IP address. Goodbye.')
                else:
                    print('Old address was %s, updating to %s' % (
                            old_ip,
                            external_ip))
                    update_record(url, headers, config, section, external_ip)
            continue # next protocol
        continue # next config secion


if __name__ == "__main__":
    main()
