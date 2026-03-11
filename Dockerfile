# Use the official Python 3.11 image as the base
FROM python:3.11

# Set the working directory inside the container
WORKDIR /app

# Unbuffer python outputs
ENV PYTHONUNBUFFERED=1

# Copy the requirements file into the container
COPY requirements.txt .

# Install the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright and its system dependencies for Chromium
RUN playwright install chromium
RUN playwright install-deps

# Copy the rest of the bot's code into the container
COPY . .

# Run the bot when the container starts
CMD ["python", "main.py"]
