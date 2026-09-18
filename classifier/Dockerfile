FROM python:3.11-slim

WORKDIR /app

# CPU-only torch build -- much smaller than the default PyPI wheel (which
# bundles CUDA libraries this service never uses), and the only option
# relevant for a Raspberry Pi anyway.
RUN pip install --no-cache-dir torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Bake the (~350MB) model into the image at build time rather than
# downloading it on first request, so container restarts don't re-fetch it
# and a cold start doesn't stall the first real classification.
ARG MODEL_NAME=umm-maybe/AI-image-detector
ENV AUTHENTIPI_CLASSIFIER_MODEL=${MODEL_NAME}
RUN python3 -c "from transformers import pipeline; pipeline('image-classification', model='${MODEL_NAME}')"

EXPOSE 8082

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8082"]
