FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app.py /app/app.py
COPY healthcheck.py /app/healthcheck.py

EXPOSE 8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_PORT=8501

HEALTHCHECK --interval=5s --timeout=2s --retries=12 --start-period=15s \
  CMD python /app/healthcheck.py || exit 1

CMD ["streamlit", "run", "/app/app.py"]
