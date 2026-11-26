# AegisFlow Backend & Frontend Setup

Verified environment versions for `backend/` and `frontend/` on branch `chore/setup-nisaruddin`:

- **Python:** 3.13.15 (`.venv`)
- **FastAPI:** 0.165.0
- **Node.js:** v20.19.5
- **npm:** 10.8.2

## Quick Start

### Backend Gateway
```powershell
.\.venv\Scripts\Activate.ps1
uvicorn backend.main:app --port 8000
```

Health check: `GET http://localhost:8000/api/v1/health`
WebSocket endpoint: `ws://localhost:8000/ws/corridor`

### Frontend Command Center
```powershell
cd frontend
npm install
npm run dev
```
