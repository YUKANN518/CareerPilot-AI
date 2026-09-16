from pydantic import BaseModel


class ApiResponse[T](BaseModel):
    success: bool = True
    data: T
    message: str = "ok"
