FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    imagemagick \
    && rm -rf /var/lib/apt/lists/*

# Allow ImageMagick to read/write all file types (needed by MoviePy)
RUN sed -i 's/rights="none" pattern="PDF"/rights="read|write" pattern="PDF"/' /etc/ImageMagick-6/policy.xml || true && \
    sed -i 's/<policy domain="coder" rights="none" pattern="MVG"/<policy domain="coder" rights="read|write" pattern="MVG"/' /etc/ImageMagick-6/policy.xml || true

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure output directories exist
RUN mkdir -p outputs/images outputs/audio

# HF Spaces requires port 7860
EXPOSE 7860

CMD ["python", "server.py"]
