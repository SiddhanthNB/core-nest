import hashlib
import secrets

from app.db.models.clients import Client


async def create_client(name: str):
    if not name or not name.strip():
        raise ValueError("Client name must be provided.")

    api_key = secrets.token_urlsafe(32)
    hashed_key = hashlib.sha256(api_key.encode()).hexdigest()

    print(f"Attempting to create client: {name}...")

    try:
        existing_clients = await Client.where(
            Client.name == name,
            Client.is_active.is_(True),
        ).aexec()
        if existing_clients:
            print(f"A client with the name '{name}' already exists and is active.")
            print("Please choose a different name OR deactivate the existing client before creating a new one.")
            return

        new_client = await Client.acreate(
            name=name,
            hashed_api_key=hashed_key,
        )

        print("\n" + "=" * 50)
        print("Client created successfully!")
        print(f"  Name: {new_client.name}")
        print(f"  API Key: {api_key}")
        print("=" * 50)
        print("Share this API key with your client. It will not be shown again.")

    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        print("Please check your database connection and configuration.")
