FROM mcr.microsoft.com/playwright/python:v1.34.0-jammy
RUN pip install asp_chef_cli
ENTRYPOINT ["python", "-m", "asp_chef_cli"]