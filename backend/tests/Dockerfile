FROM python:3.10-slim

RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    numpy \
    pandas \
    matplotlib \
    requests \
    scikit-learn \
    pyyaml \
    torch --extra-index-url https://download.pytorch.org/whl/cpu

WORKDIR /app