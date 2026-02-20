# 1. Use a slim Python base image
FROM python:3.11-slim

# 2. Set the working directory
WORKDIR /app

# 3. Install system dependencies (needed for some AI libs like OpenCV or Psycopg2)
# RUN apt-get update && apt-get install -y \
#     build-essential \
#     && rm -rf /var/lib/apt/lists/*

# 4. Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy your application code
COPY src/ ./src/

# 6. Set the command to run your script
# This is what the Container App Job will execute
CMD ["python", "src/main.py"]