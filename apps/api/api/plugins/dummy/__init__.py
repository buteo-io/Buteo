from fastapi import APIRouter

# Standard router that the loader will automatically mount
router = APIRouter(tags=["plugin-dummy"])

@router.get("")
async def get_dummy_message():
    """Return a simple JSON message to prove backend plugin integration works."""
    return {"message": "Hello from lightweight backend dummy plugin!"}
