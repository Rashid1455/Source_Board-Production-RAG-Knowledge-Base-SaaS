"""Compatibility entry point for the FastAPI service. Run migrations first."""
if __name__ == '__main__':
    import uvicorn
    uvicorn.run('backend.app.main:app',host='127.0.0.1',port=8000)
