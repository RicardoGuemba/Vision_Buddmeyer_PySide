# Realtec Vision Buddmeyer — Visão Geral

Sistema de visão computacional industrial para automação de expedição (pick-and-place) de embalagens na linha Buddmeyer.

---

## Propósito

O PC de visão comunica com o **CLP Omron NX102** via **CIP/EtherNet-IP**, detecta embalagens no campo de visão e envia coordenadas e geometria para o robô/CLP executar o ciclo de apanha e colocação.

## O que o sistema faz

1. Captura vídeo (arquivo, USB, GigE ou GenTL).
2. Executa **segmentação de instâncias** com modelo **Mask2Former** (`model_best/`), classe alvo **Embalagem**.
3. Calcula por detecção: **X, Y** (centróide da máscara), **ângulo** (eixo maior via PCA), **área** (px²) e **confiança**.
4. Orquestra o handshake com o CLP (detecção → envio → ACK → pick → place → próximo ciclo).
5. Apresenta interface desktop **PySide6** com abas Operação, Configuração e Diagnósticos.

## Stack tecnológica

| Camada | Tecnologia |
|--------|------------|
| Interface | PySide6 (Qt Widgets) |
| Visão | PyTorch, Hugging Face Transformers, Mask2Former |
| Imagem | OpenCV, Pillow, NumPy |
| Câmeras industriais | Harvesters (GenTL/GigE) |
| CLP | aphyt (CIP/EtherNet-IP) |
| Configuração | Pydantic + YAML |
| Logs | structlog (`realtec_vision.log`, `process_trace.log`) |

## Superfície do operador

- **Operação:** iniciar/parar (F5/F6), escolher fonte de vídeo, ver detecções, painel de status, console de eventos.
- **Configuração:** modelo, ROI, CLP, saída MJPEG, parâmetros de streaming.
- **Diagnósticos:** métricas, logs, saúde do sistema, contadores de ciclos.

Modos de ciclo: **manual** (operador autoriza envio e novo ciclo) ou **contínuo** (automático após handshake).

## Deployment

- **SO:** macOS 12+, Ubuntu 22.04+, Windows 10/11.
- **Python:** 3.10+ (recomendado 3.11/3.12 no box PC).
- **Modelo:** `model_best/` versionado com **Git LFS** (~181 MB).
- **GPU:** opcional — CUDA (Linux/Windows), MPS (Apple Silicon).

## Segurança operacional

- **ROI clamp:** centróide limitado à região de interesse para evitar coordenadas fora da área segura.
- **Timeouts configuráveis:** ACK, pick, place e autorização CLP.
- **Modo simulado:** PLC virtual para desenvolvimento sem hardware.
- **Logs estruturados:** rastreio de IP, tags e transições de estado.

## Mapa da documentação

| Documento | Público | Conteúdo |
|-----------|---------|----------|
| [REFERENCE.md](REFERENCE.md) | Técnico / manutenção | Arquitetura, config, CLP, testes |
| [GUIA_OPERADOR.md](GUIA_OPERADOR.md) | Operador | Uso das abas e atalhos |
| [SEGMENTATION_PIPELINE.md](SEGMENTATION_PIPELINE.md) | Visão / ML | Pipeline Mask2Former em detalhe |
| [TAG_CONTRACT.md](TAG_CONTRACT.md) | Integração CLP | Contrato de tags |
| [CLONE_BOX_PC.md](CLONE_BOX_PC.md) | Deploy | Clone, LFS, smoke test |
| [../ROTEIRO_CLIENTE.md](../ROTEIRO_CLIENTE.md) | Cliente | IP do CLP, logs, troubleshooting |
| [MACOS_SETUP.md](MACOS_SETUP.md) / [UBUNTU_SETUP.md](UBUNTU_SETUP.md) | Instalação | Por plataforma |

---

© Realtec — Buddmeyer Vision System v2.0
