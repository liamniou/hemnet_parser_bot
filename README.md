The bot fetches data from Hemnet.se ads for historical purposes.

## Prerequisites
- create bot user via [BotFather and get API token](https://core.telegram.org/bots#3-how-do-i-create-a-bot);
- Docker.

## Run the bot in Docker container
### Environment variables
Before you run the container, you need to prepare several environment variables:

| Variable           | Description                                              | Default |
| ------------------ | -------------------------------------------------------- | ------- |
| TELEGRAM_BOT_TOKEN | API token that BotFather gives you when you create a bot | -       |
| AUTHORIZED_USERS   | ID of users who can talk to the bot in DM                | -       |
| CHAT_ID            | Group chat the bot will send messages to                 | -       |
| ADMIN_CHAT_ID      | ID of user who gets log messages from the bot            | -       |


### Build Docker image for raspberry
```sh
$ docker build -f Dockerfile.arm -t hemnet_parser_bot_image .
```

### Start the container
```sh
$ docker run -it \
    --env TELEGRAM_BOT_TOKEN=PUT_BOT_TOKEN_HERE \
    --env AUTHORIZED_USERS=SOME_TG_ID \
    --env ADMIN_CHAT_ID=SOME_TG_ID \
    --env CHAT_ID=SOME_TG_CHAT_ID --name=hemnet_parser_bot hemnet_parser_bot_image
```
