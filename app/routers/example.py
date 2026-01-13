from fastapi import APIRouter

router = APIRouter(prefix="/example", tags=["Example"])


@router.get("/")
async def example():
    """Example endpoint"""
    return {"message": "Example endpoint working"}
