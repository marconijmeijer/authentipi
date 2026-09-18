FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY authentipi ./authentipi

EXPOSE 8080

CMD ["uvicorn", "authentipi.main:app", "--host", "0.0.0.0", "--port", "8080"]
