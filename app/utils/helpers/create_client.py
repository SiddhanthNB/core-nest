import hashlib
import secrets
from app.db.models.clients import Client
from app.config.postgres import get_async_db_session

async def create_client(name: str):
    if not name or not name.strip():
        raise ValueError("Client name must be provided.")

    api_key = secrets.token_urlsafe(32)
    hashed_key = hashlib.sha256(api_key.encode()).hexdigest()

    print(f"Attempting to create client: {name}...")

    try:
        async with get_async_db_session() as session:
            payload = {
                "name": name,
                "hashed_api_key": hashed_key
            }

            # check if client with the same name already exists which has is_active = True
            existing_client = await Client.fetch_records(session, {"name": name, "is_active": True})
            if existing_client:
                print(f"A client with the name '{name}' already exists and is active.")
                print("Please choose a different name OR deactivate the existing client before creating a new one.")
                return

            new_client = await Client.create_record(session, payload)

            if new_client:
                print("\n" + "="*50)
                print("Client created successfully!")
                print(f"  Name: {new_client.to_dict()['name']}")
                print(f"  API Key: {api_key}")
                print("="*50)
                print("Share this API key with your client. It will not be shown again.")
            else:
                print("\nFailed to create client. Please check the application logs for more details.")

    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        print("Please check your database connection and configuration.")
