# Pick-and-Place para Expedição de Embalagens

Buddmeyer Vision System v2.0 — Operação **sem robô físico conectado ao CLP**: processo inicia na detecção, com status de cada etapa na tela de operação, tempos realistas de expedição e modo manual por padrão.

---

## 1. Contexto: sem robô conectado ao CLP

- Não há robô real conectado ao CLP. O sistema opera com **robô simulado** (SimulatedPLC), que responde às TAGs como se existisse um robô de expedição.
- O processo começa na **deteção** pela câmera (threshold de confiança configurável). A partir daí o fluxo é: autorização (em modo manual) → envio de coordenadas ao CLP → ACK → Pick → Place → fim de ciclo.
- Todas as etapas são exibidas na **tela de operação** (barra de status e console de eventos), para o operador acompanhar a execução em tempo real.
- Os tempos de pick e place do robô simulado foram ajustados para **valores típicos de expedição** (pick ~4 s, place ~5 s), trazendo realidade ao processo.
- O **modo padrão é manual**: ao final de cada ciclo é necessário autorizar o próximo ciclo; e, após uma detecção, em modo manual o sistema **pede autorização para enviar** as coordenadas ao CLP antes de deflagar o processo.

---

## 2. Fluxo do processo (desde a detecção)

1. **Aguardar autorização do CLP**  
   Estado: `WAITING_AUTHORIZATION`. O CLP (ou simulado) deve sinalizar que autoriza a detecção (`PlcAuthorizeDetection`).

2. **Detecção**  
   Estado: `DETECTING`. A câmera e o modelo de visão detectam um objeto (embalagem) com confiança acima do threshold configurado.

3. **Modo manual: autorização para envio ao CLP**  
   Estado: `WAITING_SEND_AUTHORIZATION`.  
   - O sistema **não envia** as coordenadas automaticamente.  
   - Na tela de operação é exibido o status **"Objeto detectado. Aguardando autorização para envio ao CLP"** e o botão **"Autorizar envio ao CLP"** fica habilitado.  
   - O operador confere a detecção e clica em **"Autorizar envio ao CLP"**.  
   - Só então as coordenadas do objeto são enviadas ao CLP e o processo segue.

4. **Modo contínuo**  
   Após a detecção, as coordenadas são enviadas ao CLP automaticamente, sem etapa de autorização de envio.

5. **Envio ao CLP**  
   Estado: `SENDING_DATA`. Coordenadas (centroide X, Y em mm), confiança e demais TAGs são escritas no CLP. Status exibido: "Coordenadas enviadas ao CLP".  
   **Clamp ao ROI:** quando o checkbox "Ativar ROI" está marcado na aba Operação, qualquer centroide fora do ROI é projetado ao ponto mais próximo dentro do retângulo ROI (projeção ortogonal / mínima distância euclidiana), evitando que a plataforma de pick colida com as laterais do container.

6. **ACK do robô**  
   Estado: `WAITING_ACK`. O CLP/robô simulado confirma o recebimento. Status: "ACK do robô recebido". Tempo típico simulado: ~1,5 s.

7. **Pick**  
   Estado: `WAITING_PICK`. Simulação do robô coletando a embalagem. Status: "Aguardando PICK…" e depois "PICK concluído". Tempo típico: **~4 s** (expedição).

8. **Place**  
   Estado: `WAITING_PLACE`. Simulação do robô posicionando a embalagem. Status: "Aguardando PLACE…" e "PLACE concluído". Tempo típico: **~5 s** (expedição).

9. **Fim de ciclo**  
   Estado: `WAITING_CYCLE_START`. O CLP sinaliza ciclo completo. Status: "Ciclo pick-and-place COMPLETO". Delay típico: ~1 s.

10. **Resumo e próximo ciclo**  
    Estado: `READY_FOR_NEXT`. O sistema exibe o **resumo das etapas** no console (com timestamps).  
    - **Modo manual (padrão):** é exibido "Aguardando operador clicar 'Novo Ciclo' para continuar." O botão **"Novo Ciclo"** fica habilitado. Ao clicar, o ciclo recomeça (volta a aguardar autorização do CLP e detecção).  
    - **Modo contínuo:** o próximo ciclo inicia automaticamente.

---

## 3. Exibição de status na tela de operação

- **Barra "Status atual"**  
  Na área de controles da aba Operação, um texto em destaque indica sempre a etapa em execução, por exemplo:  
  - "Aguardando detecção"  
  - "Objeto detectado. Aguardando autorização para envio ao CLP"  
  - "Enviando coordenadas ao CLP…"  
  - "ACK recebido. Aguardando PICK…"  
  - "PICK concluído. Aguardando PLACE…"  
  - "PLACE concluído. Ciclo finalizado."  
  - "Aguardando 'Novo Ciclo' (modo manual)"

- **Console de eventos**  
  Cada etapa gera mensagens no console (com origem "Robô" ou "Ciclo"), incluindo o resumo ao final do ciclo.

- **Painel lateral**  
  Estado do robô, última detecção e contadores (detecções, ciclos, erros) são atualizados em tempo real.

---

## 4. Tempos típicos do robô simulado (expedição)

| Etapa        | Tempo (s) | Observação                          |
|-------------|-----------|-------------------------------------|
| ACK         | 1,5       | Reconhecimento da detecção pelo CLP |
| Pick        | 4,0       | Tempo típico de coleta (expedição)  |
| Place       | 5,0       | Tempo típico de posicionamento      |
| Fim de ciclo| 1,0       | Sinalização de ciclo completo      |

Esses valores podem ser ajustados no código do `SimulatedPLC` (`communication/cip_client.py`) para refletir o ritmo real da sua expedição.

---

## 5. Modo manual por padrão

- Ao abrir a aplicação, o checkbox **Modo Contínuo** está **desmarcado**, ou seja, o sistema inicia em **modo manual**.
- No modo manual:
  1. Após uma **deteção** com threshold adequado, o sistema **pede autorização** para enviar ao CLP (botão "Autorizar envio ao CLP").
  2. Após o **fim do ciclo**, o sistema **pede autorização** para o próximo ciclo (botão "Novo Ciclo").
- Assim o operador mantém controle sobre quando deflagar o envio e quando iniciar um novo ciclo, adequado para ambiente sem robô real e para validação do processo.

---

## 6. Resumo do comportamento

| Item | Comportamento |
|------|----------------|
| Robô conectado ao CLP | Não — usa robô simulado (SimulatedPLC). |
| Início do processo | Na detecção (objeto com confiança ≥ threshold). |
| Status de execução | Exibido na tela de operação (barra de status + console + painel). |
| Tempos pick/place | Ajustados para tempos típicos de expedição (~4 s pick, ~5 s place). |
| Modo padrão | Manual. |
| Modo manual – após detecção | Sistema pede autorização; ao autorizar, envia coordenadas ao CLP. |
| Modo manual – após ciclo | Sistema exibe resumo e aguarda "Novo Ciclo" para retomar. |
| Retomada do ciclo | Sempre com base no modo: manual = "Novo Ciclo"; contínuo = automático. |

---

**Documento:** v1.0  
**Projeto:** Buddmeyer Vision System v2.0 — Pick-and-Place para expedição (sem robô físico).
