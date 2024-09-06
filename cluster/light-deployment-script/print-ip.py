#!/usr/bin/env python3

import socket

def get_ip_address():
    try:
        # Get the hostname
        hostname = socket.gethostname()
        # Get the IP address
        ip_address = socket.gethostbyname(hostname)
        print(f"Host {hostname} has IP address {ip_address}")
    except Exception as e:
        print(f"Error retrieving IP address: {e}")

if __name__ == "__main__":
    get_ip_address()
