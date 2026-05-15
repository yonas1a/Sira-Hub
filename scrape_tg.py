from telethon import TelegramClient

# Replace these with your actual values from my.telegram.org
api_id = 37290821  # Your API ID (integer)
api_hash = '63e861c41a7a30c4a1c10abf4fca00cf'
channel_username = 'tikvahethiopia' # Username or link of the channel

# 'session_name' creates a file locally to keep you logged in
client = TelegramClient('my_session', api_id, api_hash)


async def main():
    # Connect to the channel
    async for message in client.iter_messages(channel_username, limit=10):
        print(f"ID: {message.id} | Date: {message.date}")
        
        # Check if message has text
        if message.text:
            print(f"Message: {message.text}")
        
        # Check if message has media (photo, video, etc.)
        if message.media:
            print(f"Media type: {type(message.media).__name__}")
            
        print("-" * 20)

with client:
    client.loop.run_until_complete(main())