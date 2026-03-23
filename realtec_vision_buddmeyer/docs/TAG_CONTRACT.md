# Contrato de Tags PC ↔ CLP

Documento técnico versionado que define o contrato de comunicação entre o sistema de visão (PC) e o CLP Omron via EtherNet/IP. Alinhado ao PRD de Correção e Aprimoramento da Comunicação PC ↔ CLP.

---

## 1. Visão geral

- **Protocolo:** EtherNet/IP (CIP), biblioteca aphyt.
- **Direções:** PC→CLP (escrita pelo PC) e CLP→PC (leitura pelo PC).
- **Tipos:** BOOL, INT, DINT, REAL conforme tabela.

---

## 2. Mapeamento PRD ↔ Implementação atual

O PRD sugere nomenclatura genérica (pc_*, plc_*). A implementação atual usa nomes específicos do projeto; a tabela abaixo relaciona ambos.

| PRD (exemplo) | Nome lógico (código) | Nome no CLP (padrão) | Tipo | Direção | Semântica |
|---------------|----------------------|------------------------|------|---------|-----------|
| pc_ready | VisionReady | VisionCtrl_VisionReady | BOOL | PC→CLP | PC inicializado/pronto |
| plc_ready | RobotReady | ROBOT_READY | BOOL | CLP→PC | CLP pronto |
| — | VisionHeartbeat | VisionCtrl_Heartbeat | BOOL | PC→CLP | Heartbeat (toggle) |
| pc_cmd_valid | VisionDataSent | VisionCtrl_DataSent | BOOL | PC→CLP | Comando/dados enviados |
| pc_x | CentroidX | CENTROID_X | REAL | PC→CLP | Coordenada X |
| pc_y | CentroidY | CENTROID_Y | REAL | PC→CLP | Coordenada Y |
| — | Confidence | CONFIDENCE | REAL | PC→CLP | Confiança (0-1) |
| — | ProductDetected | PRODUCT_DETECTED | BOOL | PC→CLP | Produto detectado |
| plc_ack (implícito) | RobotAck | ROBOT_ACK | BOOL | CLP→PC | ACK do comando |
| plc_busy | RobotBusy | RobotStatus_Busy | BOOL | CLP→PC | Executando |
| plc_done (pick) | RobotPickComplete | RobotStatus_PickComplete | BOOL | CLP→PC | Pick finalizado |
| plc_done (place) | RobotPlaceComplete | RobotStatus_PlaceComplete | BOOL | CLP→PC | Place finalizado |
| plc_fault | RobotError | ROBOT_ERROR | BOOL | CLP→PC | Falha no robô |
| — | PlcAuthorizeDetection | RobotCtrl_AuthorizeDetection | BOOL | CLP→PC | CLP autoriza detecção |
| — | PlcCycleStart | RobotCtrl_CycleStart | BOOL | CLP→PC | Novo ciclo |
| — | PlcEmergencyStop | RobotCtrl_EmergencyStop | BOOL | CLP→PC | Parada de emergência |

**Nota sobre handshake com cmd_id (PRD RF-02/RF-03):** A versão atual usa ACK booleano (RobotAck). Suporte a `pc_cmd_id`/`plc_ack_id` para idempotência pode ser adicionado em revisão futura, com novas tags opcionais no CLP.

---

## 3. Tags de escrita (PC → CLP)

| Nome lógico | Nome no CLP (padrão) | Tipo | Descrição |
|-------------|----------------------|------|-----------|
| VisionReady | VisionCtrl_VisionReady | BOOL | Sistema de visão pronto |
| VisionBusy | VisionCtrl_VisionBusy | BOOL | Sistema processando |
| VisionError | VisionCtrl_VisionError | BOOL | Erro no sistema |
| VisionHeartbeat | VisionCtrl_Heartbeat | BOOL | Heartbeat (toggle) |
| ProductDetected | PRODUCT_DETECTED | BOOL | Produto detectado |
| CentroidX | CENTROID_X | REAL | Coordenada X do centroide (mm). Se ROI ativo, coordenadas fora do ROI são projetadas ao ponto mais próximo dentro do ROI (evita colisão com plataforma). |
| CentroidY | CENTROID_Y | REAL | Coordenada Y do centroide (mm). Mesma regra de clamp ao ROI quando Ativar ROI estiver marcado. |
| Confidence | CONFIDENCE | REAL | Confiança (0-1) |
| DetectionCount | DETECTION_COUNT | INT | Contador de detecções |
| ProcessingTime | PROCESSING_TIME | REAL | Tempo de processamento (ms) |
| VisionEchoAck | VisionCtrl_EchoAck | BOOL | Echo de confirmação |
| VisionDataSent | VisionCtrl_DataSent | BOOL | Dados enviados |
| VisionReadyForNext | VisionCtrl_ReadyForNext | BOOL | Pronto para próximo ciclo |
| SystemFault | SYSTEM_FAULT | BOOL | Falha do sistema |

---

## 4. Tags de leitura (CLP → PC)

| Nome lógico | Nome no CLP (padrão) | Tipo | Descrição |
|-------------|----------------------|------|-----------|
| RobotAck | ROBOT_ACK | BOOL | ACK do robô |
| RobotReady | ROBOT_READY | BOOL | Robô pronto |
| RobotError | ROBOT_ERROR | BOOL | Erro no robô |
| RobotBusy | RobotStatus_Busy | BOOL | Robô executando |
| RobotPickComplete | RobotStatus_PickComplete | BOOL | Pick completado |
| RobotPlaceComplete | RobotStatus_PlaceComplete | BOOL | Place completado |
| PlcAuthorizeDetection | RobotCtrl_AuthorizeDetection | BOOL | CLP autoriza detecção |
| PlcCycleStart | RobotCtrl_CycleStart | BOOL | CLP solicita novo ciclo |
| PlcCycleComplete | RobotCtrl_CycleComplete | BOOL | Ciclo completo |
| PlcEmergencyStop | RobotCtrl_EmergencyStop | BOOL | Parada de emergência |
| PlcSystemMode | RobotCtrl_SystemMode | INT | Modo (0=Manual, 1=Auto, 2=Manutenção) |
| Heartbeat | SystemStatus_Heartbeat | BOOL | Heartbeat do sistema |
| SystemMode | SystemStatus_Mode | INT | Modo do sistema |
| SafetyGateClosed | Safety_GateClosed | BOOL | Portão fechado |
| SafetyAreaClear | Safety_AreaClear | BOOL | Área livre |
| SafetyLightCurtainOK | Safety_LightCurtainOK | BOOL | Cortina de luz OK |
| SafetyEmergencyStop | Safety_EmergencyStop | BOOL | Emergência não ativa |

---

## 5. Configuração

Os nomes das tags no CLP podem ser alterados via arquivo `config/config.yaml` (seção `tags`). O sistema usa o nome lógico internamente e resolve o nome físico (CLP) por essa configuração.

---

## 6. Versão

- **Documento:** v1.0  
- **Alinhado ao:** PRD Correção e Aprimoramento da Comunicação PC ↔ CLP  
- **Última atualização:** conforme implementação atual do Buddmeyer Vision v2.
