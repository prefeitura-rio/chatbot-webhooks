# Build arguments
ARG PYTHON_VERSION=3.10-slim

FROM python:${PYTHON_VERSION}

# https://docs.python.org/3/using/cmdline.html#envvar-PYTHONDONTWRITEBYTECODE
# Prevents Python from writing .pyc files to disc
ENV PYTHONDONTWRITEBYTECODE 1

# ensures that the python output is sent straight to terminal (e.g. your container log)
# without being first buffered and that you can see the output of your application (e.g. django logs)
# in real time. Equivalent to python -u: https://docs.python.org/3/using/cmdline.html#cmdoption-u
ENV PYTHONUNBUFFERED 1

# Install virtualenv and create a virtual environment
RUN pip install --no-cache-dir -U poetry && \
    poetry config virtualenvs.create false

# Copy the project files into the working directory
# and install dependencies
WORKDIR /app
COPY . .
RUN poetry install --no-dev --no-interaction --no-ansi

# Run the application
CMD ["uvicorn", "chatbot_webhooks.main:app", "--host", "0.0.0.0", "--port", "80", "--workers", "2"]
