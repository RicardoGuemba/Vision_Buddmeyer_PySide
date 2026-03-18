# Buddmeyer Vision System v2.0

Sistema de visão computacional para automação de expedição (pick-and-place) de embalagens.

## 📋 Características

- ✅ **Detecção em tempo real** usando modelos DETR/RT-DETR (Hugging Face)
- ✅ **Comunicação industrial** com CLP Omron NX102 via CIP/EtherNet-IP
- ✅ **Interface desktop PySide6** com 3 abas: Operação, Configuração, Diagnósticos
- ✅ **Múltiplas fontes de vídeo**: arquivos MP4, USB, RTSP, GigE
- ✅ **Sistema de logs** estruturado para rastreamento de detecções e erros
- ✅ **Modo simulado** para desenvolvimento sem CLP real

## 🖥️ Requisitos de Sistema

| Requisito | Valor |
|-----------|-------|
| Sistema Operacional | macOS 12+, Ubuntu 22.04+ ou Windows 10/11 |
| Python | 3.10 ou superior |
| GPU | NVIDIA CUDA (Linux/Windows) ou Apple Silicon MPS (macOS) – opcional |
| RAM | Mínimo 8 GB (recomendado 16 GB) |
| Disco | 10 GB livres |

## 🚀 Instalação

### 1. Clone ou copie o projeto

```bash
cd /caminho/para/Realtec_Vision_Buddmeyer
```

### 2. Crie um ambiente virtual

```bash
# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Instale as dependências

```bash
pip install -r realtec_vision_buddmeyer/requirements.txt
```

### 4. (Opcional) Instale suporte a GPU NVIDIA

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

## 🎮 Execução

```bash
cd realtec_vision_buddmeyer
python main.py
```

Ou a partir da raiz do repositório:

```bash
python realtec_vision_buddmeyer/main.py
```

**macOS:**
- **Duplo-clique:** use o atalho `Iniciar Realtec Vision.command` na raiz do repositório.
- **Terminal:** `./Iniciar_Realtec_Vision.sh`
- Detalhes: [docs/MACOS_SETUP.md](docs/MACOS_SETUP.md).

**Linux/Ubuntu:**
- **Terminal:** `./Iniciar_Realtec_Vision.sh`
- Detalhes e dependências de sistema: [docs/UBUNTU_SETUP.md](docs/UBUNTU_SETUP.md).

## 🧪 Testes

```bash
cd realtec_vision_buddmeyer
pip install pytest pytest-qt
python -m pytest tests/ -v
```

Inclui testes unitários (config, settings, widgets) e funcionais (inicialização, fluxo da página de Configuração).

## 📖 Documentação

- **[docs/USO_E_ABAS.md](docs/USO_E_ABAS.md)** – **tutorial de uso**: guia das abas Operação, Configuração e Diagnósticos.
- **[docs/DOCUMENTACAO_COMPLETA.md](docs/DOCUMENTACAO_COMPLETA.md)** – documentação técnica: visão geral, features, UI, arquitetura, manual de manutenção e contrato de TAGs CLP.
- **[docs/MACOS_SETUP.md](docs/MACOS_SETUP.md)** – instalação e uso no macOS.
- **[docs/UBUNTU_SETUP.md](docs/UBUNTU_SETUP.md)** – instalação e uso no Ubuntu.
- **[docs/MANUAL_GENTL(GIGE).md](docs/MANUAL_GENTL(GIGE).md)** – câmeras GigE/GenTL.
- **[ROTEIRO_CLIENTE.md](ROTEIRO_CLIENTE.md)** – passo a passo para o cliente (configuração do CLP, logs e troubleshooting).

## 📁 Estrutura do Projeto

```
realtec_vision_buddmeyer/
├── main.py                    # Ponto de entrada
├── requirements.txt           # Dependências
├── config/
│   ├── settings.py            # Pydantic Settings
│   └── config.yaml            # Configuração YAML
├── core/
│   ├── logger.py              # Sistema de logging
│   ├── metrics.py             # Coleta de métricas
│   └── exceptions.py          # Exceções customizadas
├── streaming/
│   ├── stream_manager.py      # Gerenciador de stream
│   ├── source_adapters.py     # Adaptadores de fonte
│   ├── frame_buffer.py        # Buffer de frames
│   └── stream_health.py       # Health check
├── preprocessing/
│   ├── preprocess_pipeline.py # Pipeline de pré-processamento
│   ├── roi_manager.py         # Gerenciamento de ROI
│   └── transforms.py          # Transformações de imagem
├── detection/
│   ├── inference_engine.py    # Engine de inferência
│   ├── model_loader.py        # Carregador de modelos
│   ├── postprocess.py         # Pós-processamento
│   └── events.py              # Eventos de detecção
├── communication/
│   ├── cip_client.py          # Cliente CIP/EtherNet-IP
│   ├── tag_map.py             # Mapeamento de TAGs
│   └── connection_state.py    # Estado da conexão
├── control/
│   ├── robot_controller.py    # Máquina de estados do robô
├── ui/
│   ├── main_window.py         # Janela principal
│   ├── pages/
│   │   ├── operation_page.py  # Aba Operação
│   │   ├── configuration_page.py # Aba Configuração
│   │   └── diagnostics_page.py   # Aba Diagnósticos
│   ├── widgets/
│   │   ├── video_widget.py    # Widget de vídeo
│   │   ├── status_panel.py    # Painel de status
│   │   ├── event_console.py   # Console de eventos
│   │   ├── metrics_chart.py   # Gráficos de métricas
│   │   └── log_viewer.py      # Visualizador de logs
│   └── styles/
│       └── industrial.qss     # Tema industrial
├── docs/                      # Documentação
│   ├── DOCUMENTACAO_COMPLETA.md  # Documentação principal (atual)
│   └── TAG_CONTRACT.md          # Contrato de TAGs CLP
├── models/                    # Modelos de ML
├── logs/                      # Logs do sistema
└── videos/                    # Vídeos de teste
```

## ⚙️ Configuração

Edite o arquivo `config/config.yaml` para ajustar:

### Fonte de Vídeo

```yaml
streaming:
  source_type: video  # video, usb, rtsp, gige
  video_path: videos/test.mp4
  loop_video: true
```

### Modelo de Detecção

```yaml
detection:
  default_model: PekingU/rtdetr_r50vd
  confidence_threshold: 0.5
  device: auto  # cpu, cuda, auto
```

### Comunicação CLP

```yaml
cip:
  ip: 187.99.125.5
  port: 44818
  simulated: false  # true para modo simulado
```

## 🎯 Uso

### Aba Operação

1. Selecione a fonte de vídeo (arquivo, câmera USB, RTSP, GigE)
2. Clique em **▶ Iniciar** para começar
3. Visualize as detecções em tempo real no vídeo
4. Acompanhe o status no painel lateral
5. Clique em **⏹ Parar** para encerrar

### Atalhos de Teclado

| Atalho | Ação |
|--------|------|
| F5 | Iniciar sistema |
| F6 | Parar sistema |
| F11 | Fullscreen |
| Ctrl+Q | Sair |

### Aba Configuração

- Ajuste parâmetros de vídeo, modelo, pré-processamento
- Configure a conexão com o CLP
- Teste a conexão antes de operar

### Aba Diagnósticos

- Visualize métricas em tempo real
- Acompanhe logs do sistema
- Verifique informações do sistema

## 🔧 TAGs CLP

### TAGs de Escrita (Visão → CLP)

| Nome | Tipo | Descrição |
|------|------|-----------|
| PRODUCT_DETECTED | BOOL | Produto detectado |
| CENTROID_X | REAL | Coordenada X do centroide |
| CENTROID_Y | REAL | Coordenada Y do centroide |
| CONFIDENCE | REAL | Confiança (0-1) |
| DETECTION_COUNT | INT | Contador de detecções |

### TAGs de Leitura (CLP → Visão)

| Nome | Tipo | Descrição |
|------|------|-----------|
| ROBOT_ACK | BOOL | ACK do robô |
| ROBOT_READY | BOOL | Robô pronto |
| RobotStatus_PickComplete | BOOL | Pick completado |
| RobotStatus_PlaceComplete | BOOL | Place completado |

## 📊 Métricas de Performance

| Métrica | CPU | CUDA |
|---------|-----|------|
| FPS de Inferência | ≥ 15 | ≥ 30 |
| Latência de Detecção | < 500ms | < 100ms |
| Uso de Memória | < 8 GB | < 8 GB |

## 🐛 Troubleshooting

### CUDA não detectado

Verifique se os drivers NVIDIA estão instalados:
```bash
nvidia-smi
```

Instale o PyTorch com CUDA:
```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

### Erro de conexão CLP

1. Verifique se o IP e porta estão corretos
2. Verifique a conectividade de rede
3. Ative o modo simulado para testes: `cip.simulated: true`

### Modelo não carrega

1. Verifique conexão com internet (para download do Hugging Face)
2. Ou baixe o modelo manualmente para `models/`

## 📝 Licença

© 2025 Sistema de Automação Industrial

## 🔗 Referências

- [PySide6 Documentation](https://doc.qt.io/qtforpython/)
- [PyTorch](https://pytorch.org/docs/)
- [Hugging Face Transformers](https://huggingface.co/docs/transformers/)
- [RT-DETR Model](https://huggingface.co/PekingU/rtdetr_r50vd)
- [aphyt (CIP)](https://github.com/aphyt/aphyt)
