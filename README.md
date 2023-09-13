The bot fetches data from Hemnet.se ads and sends to Telegram chat for historical purposes.

## Prerequisites
- create [MongoDB cluster](https://www.mongodb.com/cloud/atlas/register);
- create bot user via [BotFather and get API token](https://core.telegram.org/bots#3-how-do-i-create-a-bot);
- create Telegraph token (use function create_account() from app/telegraph_functions.py: `python -c 'import telegraph_functions; print(telegraph_functions.create_account("some_account"))'`)
- Docker.

## Run the bot in Docker container
### Environment variables
Before you run the container, you need to prepare several environment variables and put them to file `.env`:

| Variable                | Description                                              | Default |
| ----------------------- | -------------------------------------------------------- | ------- |
| TELEGRAM_BOT_TOKEN      | API token that BotFather gives you when you create a bot | -       |
| TELEGRAPH_TOKEN         | Token to access telegraph                                | -       |
| ADMIN_CHAT_ID           | Chat ID of a user that gets log messages                 | -       |
| CHAT_ID                 | Group chat the bot will send messages to                 | -       |
| MONGO_CONNECTION_STRING | Connection string to Mongo cluster                       | -       |
| PAGE_URL                | Hemnet.se search URL                                     | -       |

The file will look like this:
```
TELEGRAM_BOT_TOKEN=...
TELEGRAPH_TOKEN=...
ADMIN_CHAT_ID=...
CHAT_ID=...
MONGO_CONNECTION_STRING="..."
PAGE_URL=...
```

#### In order to get `CHAT_ID` of a group chat

1. Add your bot to the group.
2. Tag him in a message, i.e. `Hello @hemnet_parser_bot`
3. Call `getUpdates` for your bot: `curl https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getUpdates` and look for the `chat` item in the returned dictionary.

### Start the container
```sh
$ docker-compose up -d
```
