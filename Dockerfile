# Use a lightweight Python base image
FROM python:3.11-slim

# Create base app directory
WORKDIR /app

# Copy requirement file from the 'source' directory
COPY source/requirement.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirement.txt

# Copy 'source' and 'model' from the root into their respective folders in /app
COPY source/ /app/source/
COPY model/ /app/model/

# Set working directory to where main.py is located
WORKDIR /app/source

# Launch the forecasting engine
CMD ["python", "main.py"]