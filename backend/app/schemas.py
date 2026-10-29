# from pydantic import BaseModel, Field


# class PlanRequest(BaseModel):
#     prompt: str = Field(min_length=3, max_length=1000)


# class Channel3ChatRequest(BaseModel):
#     message: str = Field(min_length=2, max_length=1000)
#     conversation_id: str | None = Field(default=None, max_length=200)
#     budget: float | None = Field(default=None, gt=0)
#     user_id: str = Field(default="agentpay-demo-user", min_length=1, max_length=100)


# class SelectOfferRequest(BaseModel):
#     product_id: str = Field(min_length=1, max_length=160)
#     merchant: str = Field(min_length=1, max_length=200)


# class CartItem(BaseModel):
#     product_id: str = Field(min_length=1, max_length=160)
#     quantity: int = Field(ge=1, le=10)


# class ValidateCartRequest(BaseModel):
#     items: list[CartItem] = Field(min_length=1, max_length=30)
#     budget: float | None = Field(default=None, gt=0)


# class CreateOrderRequest(BaseModel):
#     items: list[CartItem] = Field(min_length=1, max_length=30)
#     budget: float | None = Field(default=None, gt=0)
#     expected_total: float | None = Field(default=None, ge=0)

from pydantic import BaseModel, Field


class PlanRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=1000)


class Channel3ChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=1000)
    conversation_id: str | None = Field(default=None, max_length=200)
    budget: float | None = Field(default=None, gt=0)
    user_id: str = Field(default="agentpay-demo-user", min_length=1, max_length=100)


class SelectOfferRequest(BaseModel):
    product_id: str = Field(min_length=1, max_length=160)
    merchant: str = Field(min_length=1, max_length=200)


class CartItem(BaseModel):
    product_id: str = Field(min_length=1, max_length=160)
    quantity: int = Field(ge=1, le=10)


class ValidateCartRequest(BaseModel):
    items: list[CartItem] = Field(min_length=1, max_length=30)
    budget: float | None = Field(default=None, gt=0)


class CreateOrderRequest(BaseModel):
    items: list[CartItem] = Field(min_length=1, max_length=30)
    budget: float | None = Field(default=None, gt=0)
    expected_total: float | None = Field(default=None, ge=0)


class PhotoSearchRequest(BaseModel):
    image_data_url: str = Field(min_length=100, max_length=12_000_000)
    prompt: str = Field(default="Find products in this photo and suggest relevant matches.", max_length=500)
    max_price: float | None = Field(default=None, gt=0)
    user_id: str = Field(default="agentpay-demo-user", min_length=1, max_length=100)


class RefundRequest(BaseModel):
    # None = full refund; a positive amount requests a partial refund.
    amount: float | None = Field(default=None, gt=0)
    note_to_payer: str = Field(default="AgentPay Sandbox refund", min_length=3, max_length=200)
    confirm: bool = Field(default=False)


class PayPalMcpCallRequest(BaseModel):
    tool_name: str = Field(min_length=1, max_length=100)
    arguments: dict = Field(default_factory=dict)
