FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD ["python", "main.py"]
```

Push that, Railway will auto-detect it and ignore nixpacks completely.

Then for your **webapp service**, go to its Settings in Railway dashboard → **Deploy** → set the Start Command to:
```
uvicorn webapp.server:app --host 0.0.0.0 --port $PORT
