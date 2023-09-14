FROM mcr.microsoft.com/playwright/python:v1.37.0-focal

WORKDIR /app

COPY ./app/requirements.txt ./

RUN pip3 install -r requirements.txt

COPY ./app/*.py ./

CMD ["python3", "hemnet_parser.py"]
