# Roteiro para o Cliente – Buddmeyer Vision v2.0

Este documento orienta o uso da aplicação no ambiente do cliente: configuração do CLP, onde ver os logs e como proceder em caso de problemas.

---

## 1. Como iniciar a aplicação

- **Pelo atalho:** use o ícone/atalho que abre o Buddmeyer Vision (por exemplo, `Iniciar_Buddmeyer_Vision.bat` na pasta do projeto).
- **Pelo terminal:** na pasta do projeto (ex.: `C:\Vision_Buddmeyer_PySide`), execute:
  ```bat
  venv\Scripts\activate
  python buddmeyer_vision_v2\main.py
  ```
- A janela principal abre com as abas **Operação**, **Configuração** e **Diagnósticos**.

---

## 2. Configurar o IP do CLP (importante)

O IP do CLP é usado **no momento em que a aplicação conecta** ao CLP. Por isso:

1. Abra a aba **Configuração**.
2. Vá até a seção **Conexão CIP/EtherNet-IP**.
3. Informe o **IP do CLP** (ex.: `192.168.1.10`) e a **Porta CIP** (em geral `44818`).
4. Clique em **Salvar** (ou use o menu Arquivo → Salvar Configurações).
5. Só depois **inicie a operação** ou **conecte ao CLP** (por exemplo, ao dar Play na aba Operação).

**Regra:** sempre que alterar o IP (ou porta), **salve as configurações** e **conecte de novo**. A aplicação lê o IP atual do arquivo de configuração cada vez que tenta conectar.

---

## 3. Onde ficam os logs (rastreio)

Os logs ajudam a conferir qual IP foi salvo, qual IP foi usado na conexão e se houve erro ao enviar tag.

- **Arquivo de log:** na pasta da aplicação, subpasta `logs`, arquivo `buddmeyer_vision.log`  
  (caminho típico: `buddmeyer_vision_v2\logs\buddmeyer_vision.log`).
- **Na interface:** na aba **Diagnósticos** há visualização de logs e métricas.

O que procurar no log:

| Mensagem no log      | Significado |
|----------------------|------------|
| `config_saved`       | Configurações foram salvas (incluindo IP e porta do CLP). |
| `cip_connecting`     | Tentativa de conexão ao CLP; o IP e a porta mostrados são os que estão sendo usados. |
| `cip_connected`      | Conexão com o CLP estabelecida. |
| `cip_simulated_mode` | Não foi possível conectar ao CLP real; a aplicação está em modo simulado. |
| `cip_error`           | Erro na comunicação (conexão ou leitura/escrita de tag); o log traz IP, porta e tag envolvidos. |

Assim você pode confirmar: (1) qual IP foi salvo (`config_saved`), (2) qual IP foi usado na conexão (`cip_connecting`) e (3) qual tag e mensagem deram erro (`cip_error`).

---

## 4. “Diz conectado, mas dá erro ao enviar a tag”

Se a aplicação indica que está conectada ao CLP mas aparece erro ao enviar alguma tag:

1. **Anote a mensagem completa** que aparece na tela (ex.: no console de eventos, em vermelho, “Erro CIP: …”).
2. **Abra o arquivo de log** `logs\buddmeyer_vision.log` e procure por `cip_error`. Lá estarão o IP, a porta e o nome da tag que falharam.
3. **No CLP (Sysmac Studio):** confira se existe uma **variável global** com o **mesmo nome** que a aplicação está usando (ex.: `VisionCtrl_VisionReady`, `PRODUCT_DETECTED`, `CENTROID_X`). O nome no projeto do CLP deve ser **igual** ao configurado na aplicação.
4. Verifique também se essas variáveis estão **publicadas para EtherNet/IP** (configuração de variáveis de rede no Sysmac Studio).

Se os nomes no CLP forem diferentes, será necessário ajustar os nomes das tags na **Configuração** da aplicação (seção de tags) para coincidir com o projeto do CLP, salvar e tentar de novo.

---

## 5. Testar se o IP está sendo lido corretamente

Foi incluído um script que verifica se, ao conectar, a aplicação usa o IP que está no arquivo de configuração (e não um IP antigo em memória).

**Como executar:**

1. Abra um terminal (Prompt de Comando ou PowerShell).
2. Vá até a pasta do projeto, por exemplo:
   ```bat
   cd C:\Vision_Buddmeyer_PySide
   ```
3. Ative o ambiente virtual (se usar):
   ```bat
   venv\Scripts\activate
   ```
4. Execute:
   ```bat
   python buddmeyer_vision_v2\scripts\test_cip_config_reload.py
   ```

**Resultado esperado:** ao final deve aparecer algo como:

`Teste de recarregamento de config: PASSOU`

E no meio do log deve aparecer `cip_connecting` com o mesmo IP que está no arquivo `config\config.yaml` (seção `cip.ip`). Isso confirma que a aplicação está usando o IP atual do config ao conectar.

---

## 6. Resumo rápido

| Ação                    | O que fazer |
|-------------------------|-------------|
| Alterar IP do CLP       | Configuração → IP do CLP → **Salvar** → depois conectar/iniciar operação. |
| Ver qual IP foi usado   | Abrir `logs\buddmeyer_vision.log` e procurar `cip_connecting`. |
| Ver erro ao enviar tag   | Ver mensagem na tela e no log (`cip_error`); conferir nome da tag no CLP (Sysmac). |
| Testar leitura do IP    | Executar `python buddmeyer_vision_v2\scripts\test_cip_config_reload.py`. |

---

## 7. Suporte

Em caso de dúvidas ou problemas não resolvidos com este roteiro, informe ao suporte:

- A mensagem de erro completa (tela e/ou log).
- Trecho do log com `config_saved`, `cip_connecting` e `cip_error` (se houver).
- Resultado do script `test_cip_config_reload.py` (se tiver sido executado).

Isso permite rastrear configuração, conexão e falhas de tag com precisão.
