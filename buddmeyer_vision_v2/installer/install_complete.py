#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Instalador Completo do Buddmeyer Vision System v2.0
Instala Python, dependências, modelos e vídeos.
"""

import sys
import os
import subprocess
import shutil
from pathlib import Path
import platform
import json

# Cores para output
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    """Imprime cabeçalho."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text.center(70)}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.RESET}\n")

def print_success(text):
    """Imprime mensagem de sucesso."""
    print(f"{Colors.GREEN}[OK] {text}{Colors.RESET}")

def print_error(text):
    """Imprime mensagem de erro."""
    print(f"{Colors.RED}[ERRO] {text}{Colors.RESET}")

def print_warning(text):
    """Imprime mensagem de aviso."""
    print(f"{Colors.YELLOW}[AVISO] {text}{Colors.RESET}")

def print_info(text):
    """Imprime informação."""
    print(f"{Colors.BLUE}[INFO] {text}{Colors.RESET}")

def check_python():
    """Verifica se Python está instalado."""
    print_info("Verificando instalação do Python...")
    
    try:
        version = sys.version_info
        if version.major >= 3 and version.minor >= 10:
            print_success(f"Python {version.major}.{version.minor}.{version.micro} encontrado")
            return True
        else:
            print_error(f"Python {version.major}.{version.minor} encontrado, mas requer Python 3.10+")
            return False
    except Exception as e:
        print_error(f"Erro ao verificar Python: {e}")
        return False

def check_pip():
    """Verifica se pip está disponível."""
    print_info("Verificando pip...")
    
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print_success("pip disponível")
            return True
        else:
            print_error("pip não encontrado")
            return False
    except Exception as e:
        print_error(f"Erro ao verificar pip: {e}")
        return False

def get_source_dir():
    """Obtém diretório fonte dos arquivos."""
    # Se executado como .exe, os arquivos estarão em _MEIPASS
    if hasattr(sys, '_MEIPASS'):
        source_dir = Path(sys._MEIPASS)
    else:
        # Modo desenvolvimento - tenta encontrar o projeto
        current_file = Path(__file__)
        # Procura o diretório buddmeyer_vision_v2
        if (current_file.parent.parent / "models").exists():
            source_dir = current_file.parent.parent
        elif (current_file.parent.parent.parent / "buddmeyer_vision_v2").exists():
            source_dir = current_file.parent.parent.parent / "buddmeyer_vision_v2"
        else:
            # Tenta diretório atual
            source_dir = Path.cwd()
    
    return source_dir

def copy_project_files(source_dir, dest_dir):
    """Copia arquivos do projeto."""
    print_info("Copiando arquivos do projeto...")
    
    project_name = "buddmeyer_vision_v2"
    source_project = source_dir / project_name
    dest_project = dest_dir / project_name
    
    # Se não encontrou no caminho esperado, tenta outros
    if not source_project.exists():
        # Tenta encontrar em diferentes locais
        possible_paths = [
            source_dir,
            source_dir / "buddmeyer_vision_v2",
            Path(__file__).parent.parent,
            Path.cwd() / "buddmeyer_vision_v2",
        ]
        
        for path in possible_paths:
            if (path / "main.py").exists() or (path / "models").exists():
                source_project = path
                break
    
    if not source_project.exists():
        print_error(f"Diretório do projeto não encontrado: {source_project}")
        return False
    
    print_info(f"Diretório fonte: {source_project}")
    
    # Remove instalação anterior
    if dest_project.exists():
        print_warning("Removendo instalação anterior...")
        shutil.rmtree(dest_project)
    
    # Copia arquivos
    try:
        shutil.copytree(source_project, dest_project, ignore=shutil.ignore_patterns(
            '__pycache__', '*.pyc', '*.pyo', '.pytest_cache', 
            '*.log', 'venv', '.git', 'dist', 'build', '*.egg-info'
        ))
        print_success("Arquivos do projeto copiados")
        return True
    except Exception as e:
        print_error(f"Erro ao copiar arquivos: {e}")
        return False

def copy_models(source_dir, dest_dir):
    """Copia modelos para o diretório correto."""
    print_info("Copiando modelos de detecção...")
    
    project_name = "buddmeyer_vision_v2"
    source_models = None
    dest_models = dest_dir / project_name / "models"
    
    # Procura modelos no diretório fonte
    possible_sources = [
        source_dir / project_name / "models",
        source_dir / "models",
        Path(__file__).parent.parent / "models",
    ]
    
    for path in possible_sources:
        if path.exists() and (path / "model.safetensors").exists():
            source_models = path
            break
    
    if source_models is None:
        print_warning("Modelos não encontrados no diretório fonte")
        print_info("Criando diretório de modelos...")
        dest_models.mkdir(parents=True, exist_ok=True)
        return True
    
    print_info(f"Copiando modelos de: {source_models}")
    
    # Cria diretório de destino
    dest_models.mkdir(parents=True, exist_ok=True)
    
    # Copia arquivos do modelo
    model_files = [
        "model.safetensors",
        "config.json",
        "preprocessor_config.json",
        "class_config.json",
        "README.md",
        "README_MODELO.md",
        "CHECKLIST_MODELO.md",
    ]
    
    copied = 0
    for file_name in model_files:
        source_file = source_models / file_name
        if source_file.exists():
            try:
                shutil.copy2(source_file, dest_models / file_name)
                copied += 1
            except Exception as e:
                print_warning(f"Erro ao copiar {file_name}: {e}")
    
    if copied > 0:
        print_success(f"Modelos copiados ({copied} arquivos)")
    else:
        print_warning("Nenhum arquivo de modelo copiado")
    
    return True

def copy_videos(source_dir, dest_dir):
    """Copia vídeos para o diretório correto."""
    print_info("Copiando vídeos de exemplo...")
    
    project_name = "buddmeyer_vision_v2"
    source_videos = None
    dest_videos = dest_dir / project_name / "videos"
    
    # Procura vídeos no diretório fonte
    possible_sources = [
        source_dir / project_name / "videos",
        source_dir / "videos",
        Path(__file__).parent.parent / "videos",
    ]
    
    for path in possible_sources:
        if path.exists() and any(path.glob("*.mp4")):
            source_videos = path
            break
    
    if source_videos is None:
        print_warning("Vídeos não encontrados no diretório fonte")
        print_info("Criando diretório de vídeos...")
        dest_videos.mkdir(parents=True, exist_ok=True)
        return True
    
    print_info(f"Copiando vídeos de: {source_videos}")
    
    # Cria diretório de destino
    dest_videos.mkdir(parents=True, exist_ok=True)
    
    # Copia vídeos
    video_extensions = ['.mp4', '.avi', '.mov', '.mkv']
    copied = 0
    
    for ext in video_extensions:
        for video_file in source_videos.glob(f"*{ext}"):
            try:
                dest_file = dest_videos / video_file.name
                if not dest_file.exists():
                    shutil.copy2(video_file, dest_file)
                    copied += 1
                    print_info(f"  Copiado: {video_file.name}")
            except Exception as e:
                print_warning(f"Erro ao copiar {video_file.name}: {e}")
    
    if copied > 0:
        print_success(f"Vídeos copiados ({copied} arquivos)")
    else:
        print_warning("Nenhum vídeo copiado")
    
    return True

def create_venv(project_dir):
    """Cria ambiente virtual."""
    print_info("Criando ambiente virtual...")
    
    venv_path = project_dir / "venv"
    
    if venv_path.exists():
        print_warning("Ambiente virtual já existe. Removendo...")
        shutil.rmtree(venv_path)
    
    try:
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv_path)],
            check=True,
            cwd=project_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print_success("Ambiente virtual criado")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Erro ao criar ambiente virtual: {e}")
        return False

def upgrade_pip(venv_python):
    """Atualiza pip no ambiente virtual."""
    print_info("Atualizando pip...")
    
    try:
        subprocess.run(
            [str(venv_python), "-m", "pip", "install", "--upgrade", "pip"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print_success("pip atualizado")
        return True
    except subprocess.CalledProcessError:
        print_warning("Erro ao atualizar pip, continuando...")
        return True

def install_dependencies(venv_python, requirements_file):
    """Instala dependências."""
    print_info("Instalando dependências Python...")
    print_info("Isso pode levar vários minutos...")
    
    # Instala dependências básicas primeiro
    basic_deps = [
        "PySide6>=6.6.0",
        "pydantic>=2.6.0",
        "pydantic-settings>=2.2.0",
        "pyyaml>=6.0.0",
        "opencv-python>=4.9.0",
        "Pillow>=10.2.0",
        "numpy>=1.24.0",
        "structlog>=24.1.0",
        "colorama>=0.4.6",
        "qasync>=0.27.0",
        "matplotlib>=3.8.0",
    ]
    
    print_info("Instalando dependências básicas...")
    try:
        subprocess.run(
            [str(venv_python), "-m", "pip", "install"] + basic_deps,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        print_success("Dependências básicas instaladas")
    except subprocess.CalledProcessError as e:
        print_error(f"Erro ao instalar dependências básicas")
        return False
    
    # Instala PyTorch com CUDA (tenta CUDA primeiro, depois CPU)
    print_info("Instalando PyTorch...")
    try:
        # Tenta CUDA primeiro
        subprocess.run(
            [
                str(venv_python), "-m", "pip", "install",
                "torch", "torchvision",
                "--index-url", "https://download.pytorch.org/whl/cu118"
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=600
        )
        print_success("PyTorch (CUDA) instalado")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        print_warning("Erro ao instalar PyTorch com CUDA, tentando CPU...")
        try:
            subprocess.run(
                [str(venv_python), "-m", "pip", "install", "torch", "torchvision"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=600
            )
            print_success("PyTorch (CPU) instalado")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            print_error("Erro ao instalar PyTorch")
            return False
    
    # Instala bibliotecas ML
    print_info("Instalando bibliotecas de Machine Learning...")
    ml_deps = [
        "transformers>=4.38.0",
        "accelerate>=0.27.0",
        "safetensors>=0.4.0",
        "timm>=0.9.0",  # Necessário para alguns modelos DETR
        "aphyt>=0.1.24",
    ]
    
    try:
        subprocess.run(
            [str(venv_python), "-m", "pip", "install"] + ml_deps,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=600
        )
        print_success("Bibliotecas ML instaladas")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print_error(f"Erro ao instalar bibliotecas ML")
        return False
    
    return True

def create_start_scripts(project_dir, venv_python):
    """Cria scripts de inicialização."""
    print_info("Criando scripts de inicialização...")
    
    # Script BAT
    bat_content = f"""@echo off
title Buddmeyer Vision System v2.0
cd /d "{project_dir}"
call venv\\Scripts\\activate.bat
python buddmeyer_vision_v2\\main.py
pause
"""
    
    bat_file = project_dir / "Iniciar_Buddmeyer_Vision.bat"
    with open(bat_file, "w", encoding="utf-8") as f:
        f.write(bat_content)
    print_success(f"Script criado: {bat_file.name}")
    
    # Script PowerShell
    ps_content = f"""# Buddmeyer Vision System v2.0
$ErrorActionPreference = "Stop"
Set-Location "{project_dir}"
& "{project_dir}\\venv\\Scripts\\Activate.ps1"
python "{project_dir}\\buddmeyer_vision_v2\\main.py"
"""
    
    ps_file = project_dir / "Iniciar_Buddmeyer_Vision.ps1"
    with open(ps_file, "w", encoding="utf-8") as f:
        f.write(ps_content)
    print_success(f"Script criado: {ps_file.name}")
    
    return True

def verify_installation(venv_python, project_dir):
    """Verifica se a instalação foi bem-sucedida."""
    print_info("Verificando instalação...")
    
    packages = [
        "PySide6",
        "torch",
        "transformers",
        "opencv-python",
        "aphyt",
    ]
    
    all_ok = True
    for package in packages:
        try:
            result = subprocess.run(
                [str(venv_python), "-m", "pip", "show", package],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                print_success(f"{package} instalado")
            else:
                print_error(f"{package} não encontrado")
                all_ok = False
        except Exception as e:
            print_error(f"Erro ao verificar {package}: {e}")
            all_ok = False
    
    # Verifica modelos
    models_dir = project_dir / "buddmeyer_vision_v2" / "models"
    if models_dir.exists() and (models_dir / "model.safetensors").exists():
        print_success("Modelos encontrados")
    else:
        print_warning("Modelos não encontrados")
    
    # Verifica vídeos
    videos_dir = project_dir / "buddmeyer_vision_v2" / "videos"
    if videos_dir.exists() and any(videos_dir.glob("*.mp4")):
        video_count = len(list(videos_dir.glob("*.mp4")))
        print_success(f"Vídeos encontrados ({video_count} arquivos)")
    else:
        print_warning("Vídeos não encontrados")
    
    return all_ok

def main():
    """Função principal do instalador."""
    print_header("BUDDMEYER VISION SYSTEM v2.0 - INSTALADOR COMPLETO")
    
    print_info(f"Sistema Operacional: {platform.system()} {platform.release()}")
    print_info(f"Arquitetura: {platform.machine()}")
    
    # Determina diretório de instalação
    if len(sys.argv) > 1:
        install_dir = Path(sys.argv[1])
    else:
        install_dir = Path.home() / "BuddmeyerVision"
    
    print_info(f"Diretório de instalação: {install_dir}")
    
    # Verifica Python
    if not check_python():
        print_error("\nPython 3.10+ é necessário!")
        print_info("Baixe em: https://www.python.org/downloads/")
        input("\nPressione Enter para sair...")
        return 1
    
    if not check_pip():
        print_error("\npip é necessário!")
        input("\nPressione Enter para sair...")
        return 1
    
    # Obtém diretório fonte
    source_dir = get_source_dir()
    print_info(f"Diretório fonte: {source_dir}")
    
    # Cria diretório de instalação
    print_info(f"Criando diretório: {install_dir}")
    install_dir.mkdir(parents=True, exist_ok=True)
    
    # Copia arquivos do projeto
    if not copy_project_files(source_dir, install_dir):
        input("\nPressione Enter para sair...")
        return 1
    
    # Copia modelos
    copy_models(source_dir, install_dir)
    
    # Copia vídeos
    copy_videos(source_dir, install_dir)
    
    # Cria ambiente virtual
    if not create_venv(install_dir):
        input("\nPressione Enter para sair...")
        return 1
    
    # Configura ambiente virtual
    if platform.system() == "Windows":
        venv_python = install_dir / "venv" / "Scripts" / "python.exe"
    else:
        venv_python = install_dir / "venv" / "bin" / "python"
    
    if not venv_python.exists():
        print_error("Python do ambiente virtual não encontrado")
        input("\nPressione Enter para sair...")
        return 1
    
    # Atualiza pip
    upgrade_pip(venv_python)
    
    # Instala dependências
    requirements_file = install_dir / "buddmeyer_vision_v2" / "requirements.txt"
    if not install_dependencies(venv_python, requirements_file):
        print_error("Falha na instalação de dependências")
        input("\nPressione Enter para sair...")
        return 1
    
    # Cria scripts de inicialização
    create_start_scripts(install_dir, venv_python)
    
    # Verifica instalação
    if verify_installation(venv_python, install_dir):
        print_header("INSTALAÇÃO CONCLUÍDA COM SUCESSO!")
        print_success(f"Sistema instalado em: {install_dir}")
        print_info("\nPara iniciar o sistema:")
        print_info(f"  1. Navegue até: {install_dir}")
        print_info(f"  2. Dê duplo clique em: Iniciar_Buddmeyer_Vision.bat")
        print_info("\nOu execute no terminal:")
        print_info(f"  cd {install_dir}")
        print_info(f"  .\\venv\\Scripts\\activate")
        print_info(f"  python buddmeyer_vision_v2\\main.py")
    else:
        print_warning("Instalação concluída com avisos")
        print_info("Algumas dependências podem não estar instaladas corretamente")
    
    input("\nPressione Enter para sair...")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nInstalação cancelada pelo usuário.")
        sys.exit(1)
    except Exception as e:
        print_error(f"\nErro inesperado: {e}")
        import traceback
        traceback.print_exc()
        input("\nPressione Enter para sair...")
        sys.exit(1)
