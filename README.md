# Replace EXE Icon v1.0

Aplicativo desktop para substituir o ícone de arquivos `.exe` no Windows, sem precisar de software externo.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue) ![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)

---

## Funcionalidades

- Selecione um ou mais arquivos `.exe` de uma vez
- Visualize o ícone atual de cada arquivo
- Escolha uma imagem nova (PNG, JPG, JPEG, GIF, WEBP ou ICO)
- Substitui o ícone diretamente nos recursos PE do executável
- O arquivo original é renomeado automaticamente para `nome_bkp.exe` como backup
- Barra de progresso por arquivo processado

---

## Requisitos

- Windows 10 ou superior
- Python 3.10 ou superior → https://www.python.org/downloads/

---

## Instalação das dependências

Abra o PowerShell e rode:

```powershell
pip install pillow pywin32 icoextract
```

| Pacote | Função |
|---|---|
| `pillow` | Abrir e converter imagens para ICO |
| `pywin32` | Manipular recursos PE do `.exe` (win32api, win32gui) |
| `icoextract` | Extrair o ícone atual do `.exe` para o preview |

---

## Como rodar direto pelo Python

```powershell
python app.py
```

---

## Como compilar para .exe

### 1. Instale o PyInstaller

```powershell
pip install pyinstaller
```

### 2. Compile

```powershell
python -m PyInstaller --onefile --windowed --name "ReplaceIcon" --icon "icone.png" --add-data "icone.png;." app.py
```

| Flag | O que faz |
|---|---|
| `--onefile` | Gera um único `.exe` sem pastas extras |
| `--windowed` | Remove a janela de console ao abrir |
| `--icon "icone.png"` | Define o ícone do próprio `.exe` gerado |
| `--add-data "icone.png;."` | Empacota o ícone dentro do `.exe` para uso em tempo de execução |

### 3. O executável gerado estará em:

```
dist\ReplaceIcon.exe
```

---

## Estrutura do projeto

```
replaceIcon/
├── app.py          # Código fonte principal
├── icone.png       # Ícone do aplicativo
├── README.md       # Este arquivo
```

---

*by Mazarati*
