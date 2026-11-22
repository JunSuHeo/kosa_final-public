import importlib
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware


def test_proxy_trust_uses_only_resolved_dedicated_network(monkeypatch):
    proxy = importlib.import_module('app.proxy')
    monkeypatch.setattr(proxy.socket, 'gethostbyname', lambda host: '172.27.0.3')
    monkeypatch.setattr(proxy.Path, 'read_text', lambda self: (
        'Iface Destination Gateway Flags RefCnt Use Metric Mask MTU Window IRTT\n'
        'eth0 00000000 01001B0A 0003 0 0 0 00000000 0 0 0\n'
        'eth0 00001B0A 00000000 0001 0 0 0 0000FFFF 0 0 0\n'
        'eth1 00001BAC 00000000 0001 0 0 0 0000FFFF 0 0 0\n'
    ))
    network = proxy.trusted_proxy_network()
    assert network == '172.27.0.0/16'
    app = FastAPI()

    @app.get('/')
    def client_address(request: Request):
        return {'host': request.client.host}

    secured = ProxyHeadersMiddleware(app, trusted_hosts=network)
    headers = {'X-Forwarded-For': '203.0.113.7'}
    with TestClient(secured, client=('172.27.0.2', 123)) as client:
        assert client.get('/', headers=headers).json()['host'] == '203.0.113.7'
    for address in ['10.27.0.2', '127.0.0.1', '198.51.100.9']:
        with TestClient(secured, client=(address, 123)) as client:
            assert client.get('/', headers=headers).json()['host'] == address


def test_missing_proxy_network_fails_closed(monkeypatch):
    proxy = importlib.import_module('app.proxy')
    monkeypatch.setattr(proxy.socket, 'gethostbyname', lambda host: '172.27.0.3')
    monkeypatch.setattr(proxy.Path, 'read_text', lambda self: (
        'Iface Destination Gateway Flags RefCnt Use Metric Mask MTU Window IRTT\n'
        'eth0 00000000 01001B0A 0003 0 0 0 00000000 0 0 0\n'
    ))
    with pytest.raises(RuntimeError, match='proxy network'):
        proxy.trusted_proxy_network()
