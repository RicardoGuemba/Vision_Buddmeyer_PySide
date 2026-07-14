# Guia do Operador — Buddmeyer Vision v2.0

Tutorial de uso das abas **Operação**, **Configuração** e **Diagnósticos**.

---

## Antes de começar

1. Instale o ambiente (ver [MACOS_SETUP.md](MACOS_SETUP.md) ou [UBUNTU_SETUP.md](UBUNTU_SETUP.md)).
2. Confirme que `model_best/` está completo (`git lfs pull` se clonou do GitHub).
3. Configure o IP do CLP na aba **Configuração** e **salve** antes de operar.

---

## Aba Operação

### Iniciar o sistema

1. Escolha a **fonte de vídeo** no combo: Arquivo, USB, GigE ou GenTL.
2. Clique **▶ Iniciar** (ou **F5**).
3. Aguarde o carregamento do modelo (barra de status). Na primeira execução pode demorar alguns segundos.
4. As detecções aparecem sobre o vídeo (máscara/contorno da embalagem).

### Parar

- **⏹ Parar** ou **F6** — para stream, inferência e handshake com CLP.

### Painel de status

Exibe em tempo real:

- Estado do ciclo / robô
- Última detecção: confiança, **X, Y, ângulo (°), área**
- Conexão CLP e latência
- FPS de captura e inferência

### Modos de ciclo

| Modo | Comportamento |
|------|---------------|
| **Manual** | Após detecção, operador autoriza envio ao CLP; após ciclo, clica **Novo Ciclo** |
| **Contínuo** | Ciclos seguem automaticamente após handshake |

### ROI (região de interesse)

- Ajuste o retângulo ROI na Operação para limitar a área de detecção.
- O centróide enviado ao CLP é **limitado ao ROI** (segurança).

### Stream para navegador (MJPEG)

Se habilitado em Configuração → Saída, abra no browser:

`http://<IP-do-PC>:8080/stream`

### Atalhos

| Atalho | Ação |
|--------|------|
| F5 | Iniciar |
| F6 | Parar |
| F11 | Fullscreen |
| Ctrl+Q | Sair |

### Câmera GenTL

Com fonte **GenTL**, use o botão de ajustes para exposição/ganho quando disponível.

---

## Aba Configuração

Sub-abas: **Entrada**, **Detecção**, **Imagem**, **CLP**, **Saída**.

### Entrada

Parâmetros por fonte: caminho do vídeo, índice USB, IP GigE, CTI GenTL, etc.

### Detecção

- Modelo: padrão `model_best` (Mask2Former treinado para Embalagem).
- Limiar de confiança: valores altos reduzem falsos positivos mas podem silenciar detecções reais — use logs `inference_diagnostic` para calibrar.

### Imagem / ROI

- ROI e calibração mm/px para exibição de coordenadas em mm.

### CLP

- IP, porta, modo simulado.
- **Salvar** após alterar IP — a conexão usa o valor do ficheiro no momento do connect.

### Saída

- Stream HTTP MJPEG (campo `rtsp_enabled` no YAML é nome legado).

**Importante:** parâmetros avançados de segmentação (`segmentation_*`, `target_classes`) estão apenas em `config/config.yaml`.

---

## Aba Diagnósticos

- **Visão geral:** contadores (detecções, ciclos, erros), saúde do sistema.
- **Métricas:** gráficos de FPS e latência.
- **Logs:** visualização de `realtec_vision.log`.
- **Sistema:** informações de hardware e versão.

---

## Fluxo típico pick-and-place

1. CLP autoriza detecção (`RobotCtrl_AuthorizeDetection`).
2. Visão detecta embalagem → envia X, Y, ângulo, área, confiança.
3. Robô confirma ACK → executa pick → place.
4. Ciclo completa → pronto para próximo (manual ou automático).

Detalhe da máquina de estados: [PICK_PLACE_EXPEDICAO.md](PICK_PLACE_EXPEDICAO.md).

---

## Problemas comuns

| Problema | O que fazer |
|----------|-------------|
| Tela preta (USB) | Aguarde warm-up; troque índice da câmera; veja log `inference_diagnostic` |
| Nenhuma detecção | Baixe `confidence_threshold`; verifique iluminação e ROI |
| CLP desconectado | Confira IP, cabo, firewall; teste modo simulado |
| Erro ao enviar tag | Compare nomes das tags com Sysmac Studio — ver [ROTEIRO_CLIENTE.md](../ROTEIRO_CLIENTE.md) |

---

## Documentação adicional

- [OVERVIEW.md](OVERVIEW.md) — visão executiva
- [REFERENCE.md](REFERENCE.md) — referência técnica
- [ROTEIRO_CLIENTE.md](../ROTEIRO_CLIENTE.md) — suporte e logs
