import gandi_ddns as script
import requests
import subprocess

def test_get_ip():
    assert script.get_ip('4') == requests.get("http://ipecho.net/plain?").text

    # damn, I used curl here so I could get the test value from ipify.org,
    # but for some reason ipify.org's IPv6 address has disappeard from
    # DNS.  I swear it worked the other day...

    proc = subprocess.run(["curl", "-6", "https://ifconfig.co/"], stdout=True)
    if proc.returncode != 0:
        print('IPv6 test skipped, probably \"curl\" is not available')
        print('as would be expected on Windows.')
        return

    assert script.get_ip('6') == proc.output.rstrip()
