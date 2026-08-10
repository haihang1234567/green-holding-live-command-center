from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    team_id: int | None = None
    username: str


class MockStartRequest(BaseModel):
    channel_id: int
    team_id: int
    shift: str = "MORNING"


class MockChannelRequest(BaseModel):
    channel_id: int


class MockSessionRequest(BaseModel):
    session_id: int


class MockOrdersRequest(BaseModel):
    session_id: int
    count: int = 1


class MockMoneyRequest(BaseModel):
    session_id: int
    amount: int


class AckAlertRequest(BaseModel):
    acknowledged: bool = True


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
