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
class SettingUpdate(BaseModel):
    value: str
class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: str = "TEAM"
    team_id: int | None = None
class UserActiveRequest(BaseModel):
    active: bool
class ChannelUpdateRequest(BaseModel):
    name: str | None = None
    external_channel_id: str | None = None
    tiktok_shop_id: str | None = None
    advertiser_id: str | None = None
class AssignmentUpdateRequest(BaseModel):
    team_id: int | None = None
    shift: str | None = None
    start_hour: int | None = None
    end_hour: int | None = None
    active: bool | None = None
class ManualLiveStartRequest(BaseModel):
    channel_id: int
    team_id: int
    shift: str = "MORNING"
