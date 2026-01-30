#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Testa se o CIPClient usa o IP/porta atual do config ao conectar
(recarregamento no connect() em vez de só no init).

Como executar (a partir da pasta do projeto, ex.: C:\\Vision_Buddmeyer_PySide):
  python buddmeyer_vision_v2/scripts/test_cip_config_reload.py

Ou, a partir da pasta buddmeyer_vision_v2:
  python scripts/test_cip_config_reload.py
"""

import sys
from pathlib import Path

# Garante que o módulo da aplicação (buddmeyer_vision_v2) está no path
_app_root = Path(__file__).resolve().parent.parent
if str(_app_root) not in sys.path:
    sys.path.insert(0, str(_app_root))

import asyncio
from config import get_settings
from communication import CIPClient


async def test_reload_on_connect():
    """Verifica que connect() recarrega IP/porta do config."""
    # Config atual
    settings = get_settings(reload=True)
    ip_config = settings.cip.ip
    port_config = settings.cip.port
    print(f"Config atual: IP={ip_config}, port={port_config}")

    client = CIPClient()
    # Garante desconectado para que connect() execute _reload_connection_config
    await client.disconnect()
    print(f"CIPClient apos init: _ip={client._ip}, _port={client._port}")

    # Simula valor antigo em memoria (como antes da correcao)
    client._ip = "192.168.1.99"
    client._port = 9999
    print(f"Simulando IP antigo em memoria: _ip={client._ip}")

    # connect() deve recarregar e usar config
    connected = await client.connect()
    print(f"Apos connect(): _ip={client._ip}, _port={client._port}")
    print(f"state.ip={client._state.ip}, state.port={client._state.port}")

    # Deve ter voltado ao valor do config
    assert client._ip == ip_config, f"Esperado _ip={ip_config}, obteve {client._ip}"
    assert client._port == port_config, f"Esperado _port={port_config}, obteve {client._port}"
    assert client._state.ip == ip_config
    assert client._state.port == port_config
    print("OK: connect() recarrega IP/porta do config.")

    # Desconecta para nao deixar aberto
    await client.disconnect()
    return True


if __name__ == "__main__":
    asyncio.run(test_reload_on_connect())
    print("\nTeste de recarregamento de config: PASSOU")
