# Use an official Python runtime as a parent image
FROM python:3.11-alpine

# Set the working directory to /app
WORKDIR /app

# Install necessary packages and dependencies
RUN apk --no-cache add \
    gcc \
    musl-dev \
    libffi-dev \
    openssl-dev \
    python3-dev \
    py3-pip \
    && pip3 install --upgrade pip

# Install BACpypes3 and aiohttp
RUN pip3 install bacpypes3 aiohttp

# Copy the current directory contents into the container at /app
COPY . /app

# Define environment variable
ENV NAME bacnet_dr_server

# Run app.py when the container launches
CMD ["python", "bacnet_server.py"]
