# Multistage build to decrease build size
# Stage 1: Build dependencies (with compiler, etc.)
FROM python:alpine AS builder

RUN apk add --no-cache \
    gcc \
    g++ \
    make \
    musl-dev \
    libffi-dev \
	lapack-dev \
    blas-dev \
    openblas-dev \
    lapack-dev \
    ffmpeg \
    curl

WORKDIR /build

COPY requirements.txt ./
RUN pip install --upgrade pip setuptools wheel --root-user-action=ignore
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt --root-user-action=ignore

# Stage 2: Final runtime image
FROM python:alpine

RUN apk add --no-cache \
    ffmpeg \
    curl \
	openblas

WORKDIR /app

RUN mkdir -p /app/config \
    ln -s /app/config /config

COPY --from=builder /install /usr/local
COPY . .

RUN pip install . --no-cache-dir --root-user-action=ignore

ENV PYTHONUNBUFFERED=1
ENV C2S_CONFIG_PATH=/config/config.ini

VOLUME ["/config"]

ENTRYPOINT ["python", "-m", "clips2share.clips2share"]