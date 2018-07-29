#!/bin/bash
# sample script for registering via gandi_ddns.py when a network
# interface is brought up,
# it assumes:
#    network is managed by NetworkManager
#    systemd and journald are in use
# whether that's true depends on the Linux distro and version...

# install this script in /etc/NetworkManager/dispatcher.d/99-register-dns,
# make sure it's executable.

# it's executed by NetworkManager at network configuration changes.

# set the following variables according to your setup:

# fully qualified location of gandi_ddns.py
GANDI_DDNS=/home/rfm/gandi-ddns/gandi_ddns.py

# user to execute gandi_ddns.py as.  user should not have any special
# privileges (i.e. don't use root) except it must be able to read
# files in $GANDI_DDNS.
EXECUSER=rfm

# Public network interface name.  This is used to avoid calling
# gandi_ddns multiple times (since we'll be invoked for the loopback,
# even if the system only has one real nic.)
INTERFACE=enp0s3

if [[ "$1" != "$INTERFACE" || "$2" != "up" ]]
then
    # whatever this event is, it isn't the public interface coming up
    exit 0
fi

/bin/su -c "systemd-cat -t 'ddns' python3 $GANDI_DDNS" "$EXECUSER"
