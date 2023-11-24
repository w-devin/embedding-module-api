FROM python:3.10-slim

WORKDIR /app

COPY embedding_api.py requirements.txt /app/

RUN pip install -r requirements.txt

EXPOSE 6006

CMD ["python3", "embedding_api.py", "moka-ai/m3e-large"]