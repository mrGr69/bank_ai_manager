from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bank: Mapped[str] = mapped_column(String(16), index=True)
    code: Mapped[str] = mapped_column(String(32), index=True)
    external_id: Mapped[str] = mapped_column(String(128), default="")
    title: Mapped[str] = mapped_column(String(128))
    currency: Mapped[str] = mapped_column(String(8), default="UAH")
    credit_limit_uah: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    last_balance_uah: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    last_debt_uah: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account")

    __table_args__ = (UniqueConstraint("bank", "code", name="uq_account_bank_code"),)


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    source: Mapped[str] = mapped_column(String(24), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    external_id: Mapped[str] = mapped_column(String(128), default="")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    description: Mapped[str] = mapped_column(Text)
    mcc: Mapped[str] = mapped_column(String(8), default="")
    amount_uah: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    original_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    original_currency: Mapped[str] = mapped_column(String(8), default="UAH")
    fee_uah: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    cashback_uah: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    balance_after: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    bank_category: Mapped[str] = mapped_column(String(64), default="")
    card_mask: Mapped[str] = mapped_column(String(32), default="")
    category: Mapped[str] = mapped_column(String(32), index=True, default="UNCATEGORIZED_SUSPICIOUS")
    confidence: Mapped[float] = mapped_column(default=0.5)
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    exclude_from_budget: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_anomaly: Mapped[bool] = mapped_column(Boolean, default=False)
    is_essential: Mapped[bool] = mapped_column(Boolean, default=False)
    budget_impact: Mapped[str] = mapped_column(String(16), default="LOW")
    clarification_needed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    clarification_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    clarification_options: Mapped[list | None] = mapped_column(JSON, nullable=True)
    coach_comment: Mapped[str] = mapped_column(Text, default="")
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    classified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account: Mapped[Account] = relationship(back_populates="transactions")


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class MerchantRule(Base):
    __tablename__ = "merchant_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pattern: Mapped[str] = mapped_column(String(128), unique=True)
    category: Mapped[str] = mapped_column(String(32))
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False)
    is_essential: Mapped[bool] = mapped_column(Boolean, default=False)
    exclude_from_budget: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(String(255), default="")


class AlertLog(Base):
    __tablename__ = "alert_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transaction_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    fingerprint: Mapped[str] = mapped_column(String(80), unique=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
