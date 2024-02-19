FROM mcr.microsoft.com/playwright/python:v1.34.0-jammy
RUN pip install asp_chef_cli==0.2.0 --upgrade
ENTRYPOINT ["python", "-m", "asp_chef_cli"]