FROM python:3.8

WORKDIR /app

COPY ./app/requirements.txt ./

RUN pip install -r requirements.txt

COPY ./app/hemnet_parser_bot.py ./

CMD ["python", "hemnet_parser_bot.py"]