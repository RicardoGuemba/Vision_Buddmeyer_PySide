# Changelog

## [Unreleased] – Correção IP/CLP e roteiro cliente

### Corrigido

- **IP do CLP não atualizava após alterar na tela:** o backend usava o IP carregado apenas na inicialização. Agora, a cada tentativa de **conexão**, a aplicação recarrega IP, porta e timeout do arquivo de configuração (e da UI após salvar). Assim, alterar o IP na Configuração, salvar e conectar passa a usar o IP novo.
- **Rastreio por log:**
  - Ao **salvar** configurações: log `config_saved` com `cip_ip`, `cip_port` e caminho do arquivo.
  - Ao **conectar** ao CLP: log `cip_connecting` com IP, porta, timeout e modo simulado usados.
  - Em **erros CIP** (conexão ou tag): log `cip_error` com IP, porta, tag (quando aplicável) e mensagem de erro.

### Adicionado

- **ROTEIRO_CLIENTE.md:** guia para o cliente com:
  - Como iniciar a aplicação.
  - Como configurar o IP do CLP (salvar e depois conectar).
  - Onde ficam os logs e o que procurar (`config_saved`, `cip_connecting`, `cip_error`).
  - O que fazer quando “diz conectado mas dá erro ao enviar tag”.
  - Como executar o teste de recarregamento de config (`test_cip_config_reload.py`).
- **Script de teste** `scripts/test_cip_config_reload.py`: verifica se, ao conectar, o sistema usa o IP atual do config (pode ser executado a partir da pasta do projeto ou de `buddmeyer_vision_v2`).
- Referência ao **ROTEIRO_CLIENTE.md** no README principal.

### Alterações técnicas

- `communication/cip_client.py`:
  - Novo método `_reload_connection_config()` para recarregar IP/porta/timeout do config.
  - `connect()` chama `_reload_connection_config()` antes de conectar e registra `cip_connecting`.
  - `_handle_error()` passa a receber `tag_name` opcional e registra `cip_error` com IP, porta e tag.
- `ui/pages/configuration_page.py`: ao salvar configurações, registra `config_saved` com `cip_ip` e `cip_port`.
