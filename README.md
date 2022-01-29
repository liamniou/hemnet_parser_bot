The bot fetches data from Hemnet.se ads and sends to Telegram chat for historical purposes.

## Prerequisites
- create [MongoDB cluster](https://www.mongodb.com/cloud/atlas/register);
- create bot user via [BotFather and get API token](https://core.telegram.org/bots#3-how-do-i-create-a-bot);
- fetch Telegraph token (use function create_account() from app/telegraph_functions.py)
- Docker.

## Run the bot in Docker container
### Environment variables
Before you run the container, you need to prepare several environment variables:

| Variable                | Description                                              | Default |
| ----------------------- | -------------------------------------------------------- | ------- |
| TELEGRAM_BOT_TOKEN      | API token that BotFather gives you when you create a bot | -       |
| TELEGRAPH_TOKEN         | Token to access telegraph                                | -       |
| ADMIN_CHAT_ID           | Chat ID of a user that gets log messages                 | -       |
| CHAT_ID                 | Group chat the bot will send messages to                 | -       |
| MONGO_CONNECTION_STRING | Connection string to Mongo cluster                       | -       |


### Build Docker image for ARM
```sh
$ docker build -f Dockerfile.arm -t hemnet_parser_bot_image .
```

### Start the container
```sh
$ docker run -dit \
    --env TELEGRAM_BOT_TOKEN=PUT_BOT_TOKEN_HERE \
    --env TELEGRAPH_TOKEN=PUT_TELEGRAPH_TOKEN_HERE \
    --env ADMIN_CHAT_ID=SOME_TG_ID \
    --env CHAT_ID=SOME_TG_CHAT_ID \
    --env MONGO_CONNECTION_STRING=PUT_CONN_STRING_HERE \
    --name=hemnet_parser_bot hemnet_parser_bot_image
```
