# Instalador Windows — Buddmeyer Vision

Guia para gerar e usar o instalador PyInstaller no Windows.

## Gerar o instalador

O ficheiro `.exe` **não está versionado** no repositório. Gere localmente:

```powershell
cd realtec_vision_buddmeyer\installer
python build_installer.py
```

Saída esperada: `installer/dist/BuddmeyerVisionInstaller.exe`

Ficheiros envolvidos:
- `installer/install.py` — lógica de instalação
- `installer/BuddmeyerVisionInstaller.spec` — spec PyInstaller

## Executar o instalador

1. Duplo-clique em `BuddmeyerVisionInstaller.exe`
2. O instalador:
   - Verifica **Python 3.10+** no sistema
   - Copia o projeto para `C:\Users\[Usuário]\BuddmeyerVision` (padrão)
   - Cria ambiente virtual e instala dependências
   - Inclui modelo **Mask2Former** em `model_best/`
3. Após conclusão, inicie com `Iniciar_Buddmeyer_Vision.bat` ou:
   ```powershell
   cd C:\Users\[Usuário]\BuddmeyerVision
   .\venv\Scripts\activate
   python realtec_vision_buddmeyer\main.py
   ```

## Requisitos

- Windows 10/11
- Python 3.10+ instalado e no PATH
- ~10 GB disco livre
- Internet (PyTorch e dependências)

## Dependências instaladas

- PySide6 (interface)
- PyTorch + Transformers (Mask2Former)
- OpenCV, NumPy, Pillow
- aphyt (CIP/EtherNet-IP)
- Demais pacotes em `requirements.txt`

## Troubleshooting

| Problema | Solução |
|----------|---------|
| Python não encontrado | Instalar de python.org com "Add to PATH" |
| Falha em dependências | Executar como Administrador; verificar rede |
| Modelo ausente | Confirmar que `model_best/` foi copiado na instalação |

## Documentação

- [docs/CLONE_BOX_PC.md](../docs/CLONE_BOX_PC.md) — alternativa sem instalador (git clone + LFS)
- [docs/REFERENCE.md](../docs/REFERENCE.md) — referência técnica
