# Sova Backend Startup Script
# Run with: powershell -ExecutionPolicy Bypass -File D:\Anshul\project\sova-ai\backend\sova-backend-startup.ps1

$BackendDir = "D:\Anshul\project\sova-ai\backend"
$PythonExe = "python"

# Change to backend directory
Set-Location -Path $BackendDir

# Set environment variables for local development
$env:BACKEND_API = "http://127.0.0.1:8000/api"

# Run the backend
& $PythonExe -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload