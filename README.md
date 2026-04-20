# Cogitate Unified Engine

Unified local dev workspace for:

- Schema Rater (React + Vite + FastAPI)
- Excel Rater (Next.js + FastAPI + win32com)
- Proxy Gateway (Express reverse proxy)

The single entrypoint is the gateway at http://localhost:8080.

## Services and Ports

- Proxy Gateway: 8080
- Schema Rater Frontend (Vite): 5173
- Schema Rater Backend (FastAPI): 8000
- Excel Rater Frontend (Next.js): 3000
- Excel Rater Backend (FastAPI): 8001

## Prerequisites

- Windows
- Node.js 18+
- npm 9+
- Python 3.11+ (venv support)
- Microsoft Excel installed (required for Excel Rater backend with win32com)

## First-Time Setup (One-Time)

Run these from the workspace root unless noted.

### 1) Install root dependencies (gateway + orchestration scripts)

```powershell
npm install
```

### 2) Install both frontend dependencies

```powershell
npm run install:frontends
```

### 3) Create and prepare Schema backend virtual environment

```powershell
cd schema-rater
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install fastapi uvicorn python-multipart openpyxl formulas pydantic numpy
deactivate
cd ..
```

### 4) Create and prepare Excel backend virtual environment

```powershell
cd "excel-rater/cogitate rater/backend"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
deactivate
cd ../../..
```

### 5) Start all five services

```powershell
npm run dev
```

Then open:

- http://localhost:8080

## Daily Run (What You Repeat)

You do not need to repeat the full 5-step setup every time.

Normally, each new dev session only needs:

```powershell
npm run dev
```

Use setup steps again only when:

- New machine / fresh clone
- You deleted virtual environments or node_modules
- requirements.txt or package dependencies changed

## Helpful Commands

### Reinstall only frontends

```powershell
npm run install:frontends
```

### Reinstall Schema backend packages

```powershell
.\schema-rater\.venv\Scripts\python -m pip install -U pip setuptools wheel
.\schema-rater\.venv\Scripts\python -m pip install fastapi uvicorn python-multipart openpyxl formulas pydantic numpy
```

### Reinstall Excel backend packages

```powershell
.\excel-rater\cogitate rater\backend\.venv\Scripts\python -m pip install -U pip setuptools wheel
.\excel-rater\cogitate rater\backend\.venv\Scripts\python -m pip install -r .\excel-rater\cogitate rater\backend\requirements.txt
```

## Troubleshooting

### "ModuleNotFoundError: No module named pip"

Use interpreter-bound pip for each env instead of plain pip:

```powershell
.\schema-rater\.venv\Scripts\python -m pip --version
.\excel-rater\cogitate rater\backend\.venv\Scripts\python -m pip --version
```

If needed, repair pip in a venv:

```powershell
.\schema-rater\.venv\Scripts\python -m ensurepip --upgrade
.\schema-rater\.venv\Scripts\python -m pip install --force-reinstall pip

.\excel-rater\cogitate rater\backend\.venv\Scripts\python -m ensurepip --upgrade
.\excel-rater\cogitate rater\backend\.venv\Scripts\python -m pip install --force-reinstall pip
```

### Excel backend fails to calculate

- Ensure Microsoft Excel opens normally outside the app.
- Close stray EXCEL.EXE processes from Task Manager.
- If files came from internet/email, open file properties and unblock if needed.

## Notes

- Root script npm run dev starts all five services together.
- Gateway routing is selection-based from the splash screen and stays on port 8080 for unified UX.
