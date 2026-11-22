"""Docker API launcher: trust only the dedicated nginx network's allocated CIDR."""
from ipaddress import IPv4Address, IPv4Network
from pathlib import Path
import socket
import uvicorn


def trusted_proxy_network():
    address = IPv4Address(socket.gethostbyname('studio-proxy-api'))
    # Linux Docker allocates a different subnet for each Compose project. The
    # unique alias identifies this container's interface on the nginx network.
    for line in Path('/proc/net/route').read_text().splitlines()[1:]:
        fields = line.split()
        if fields[2] != '00000000' or fields[7] == '00000000':
            continue
        destination = socket.inet_ntoa(bytes.fromhex(fields[1])[::-1])
        mask = socket.inet_ntoa(bytes.fromhex(fields[7])[::-1])
        network = IPv4Network((destination, mask))
        if address in network:
            return str(network)
    raise RuntimeError('Dedicated proxy network route is missing')


if __name__ == '__main__':
    uvicorn.run('app.main:app', host='0.0.0.0', port=8000,
                proxy_headers=True, forwarded_allow_ips=trusted_proxy_network())
