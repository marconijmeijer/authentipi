FROM mitmproxy/mitmproxy:latest

ENV PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir c2pa-python==0.37.10 requests==2.32.3

COPY authentipi_addon.py /addons/authentipi_addon.py

EXPOSE 8081

CMD ["mitmdump", "--mode", "regular", "--listen-port", "8081", "-s", "/addons/authentipi_addon.py"]
