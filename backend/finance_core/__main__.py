import uvicorn


if __name__ == "__main__":
    uvicorn.run("finance_core.main:app", host="127.0.0.1", port=8788, reload=True)
