import uuid

from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    email = Column(Text, unique=True, nullable=False)
    full_name = Column(Text, server_default="")
    is_admin = Column(Boolean, server_default="false")
    subscription_tier = Column(Text, server_default="free")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    broker_credentials = relationship("BrokerCredential", back_populates="profile")
    orders = relationship("Order", back_populates="profile")
    trades = relationship("Trade", back_populates="profile")
    risk_settings = relationship("RiskSetting", back_populates="profile")


class BrokerCredential(Base):
    __tablename__ = "broker_credentials"
    __table_args__ = (UniqueConstraint("user_id", "broker"),)

    id = Column(UUID, primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(UUID, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    broker = Column(Text, nullable=False)
    encrypted_api_key = Column(Text, nullable=False)
    encrypted_secret_key = Column(Text, nullable=False)
    encrypted_access_token = Column(Text, server_default="")
    encrypted_refresh_token = Column(Text, server_default="")
    additional_params = Column(JSONB, server_default="{}")
    is_active = Column(Boolean, server_default="true")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    profile = relationship("Profile", back_populates="broker_credentials")


class Strategy(Base):
    __tablename__ = "strategies"

    id = Column(UUID, primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(UUID, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    type = Column(Text, server_default="builtin")
    config = Column(JSONB, server_default="{}")
    is_active = Column(Boolean, server_default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    runs = relationship("StrategyRun", back_populates="strategy")


class StrategyRun(Base):
    __tablename__ = "strategy_runs"

    id = Column(UUID, primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(UUID, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    strategy_id = Column(UUID, ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False)
    broker = Column(Text, nullable=False)
    mode = Column(Text, server_default="PAPER")
    symbols = Column(ARRAY(Text), server_default="{}")
    status = Column(Text, server_default="stopped")
    started_at = Column(DateTime(timezone=True))
    stopped_at = Column(DateTime(timezone=True))
    daily_pnl = Column(Float, server_default="0")
    total_pnl = Column(Float, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    strategy = relationship("Strategy", back_populates="runs")


class RiskSetting(Base):
    __tablename__ = "risk_settings"
    __table_args__ = (UniqueConstraint("user_id", "strategy_id"),)

    id = Column(UUID, primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(UUID, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    strategy_id = Column(UUID, ForeignKey("strategies.id", ondelete="CASCADE"), nullable=True)
    max_capital = Column(Float, server_default="0")
    max_position_size = Column(Float, server_default="0")
    max_open_positions = Column(Integer, server_default="10")
    max_daily_loss = Column(Float, server_default="0")
    max_drawdown_pct = Column(Float, server_default="0")
    max_exposure = Column(Float, server_default="0")
    max_symbol_exposure = Column(Float, server_default="0")
    max_quantity = Column(Integer, server_default="0")
    max_trades_per_day = Column(Integer, server_default="0")
    trading_start = Column(Text, server_default="09:15")
    trading_end = Column(Text, server_default="15:30")
    daily_profit_target = Column(Float, server_default="0")
    kill_switch_enabled = Column(Boolean, server_default="false")
    is_live = Column(Boolean, server_default="false")
    emergency_stop = Column(Boolean, server_default="false")
    allow_warning = Column(Boolean, server_default="true")
    broker_blocked = Column(JSONB, server_default="[]")
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    profile = relationship("Profile", back_populates="risk_settings")


class Order(Base):
    __tablename__ = "orders"

    id = Column(UUID, primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(UUID, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    strategy_id = Column(UUID, ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True)
    broker = Column(Text, nullable=False)
    symbol = Column(Text, nullable=False)
    exchange = Column(Text, nullable=False)
    side = Column(Text, nullable=False)
    order_type = Column(Text, nullable=False)
    product = Column(Text, nullable=False)
    quantity = Column(Integer, nullable=False)
    price = Column(Float, server_default="0")
    status = Column(Text, server_default="PENDING")
    filled_quantity = Column(Integer, server_default="0")
    average_price = Column(Float, server_default="0")
    message = Column(Text, server_default="")
    is_paper = Column(Boolean, server_default="true")
    client_order_id = Column(Text, server_default="")
    broker_order_id = Column(Text, server_default="")
    trigger_price = Column(Float, nullable=True)
    instrument_type = Column(Text, server_default="EQ")
    strike_price = Column(Float, nullable=True)
    expiry_date = Column(Text, nullable=True)
    option_type = Column(Text, nullable=True)
    source = Column(Text, server_default="manual")
    signal_at = Column(DateTime(timezone=True), nullable=True)
    risk_checked_at = Column(DateTime(timezone=True), nullable=True)
    filled_at = Column(DateTime(timezone=True), nullable=True)
    latency_ms = Column(Float, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    profile = relationship("Profile", back_populates="orders")


class Trade(Base):
    __tablename__ = "trades"

    id = Column(UUID, primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(UUID, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    order_id = Column(UUID, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    strategy_id = Column(UUID, ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True)
    broker = Column(Text, nullable=False)
    symbol = Column(Text, nullable=False)
    exchange = Column(Text, nullable=False)
    side = Column(Text, nullable=False)
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    value = Column(Float, nullable=False)
    trade_time = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_paper = Column(Boolean, server_default="true")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    profile = relationship("Profile", back_populates="trades")


class PositionSnapshot(Base):
    __tablename__ = "positions_snapshot"
    __table_args__ = (UniqueConstraint("user_id", "broker", "symbol"),)

    id = Column(UUID, primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(UUID, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    broker = Column(Text, nullable=False)
    symbol = Column(Text, nullable=False)
    exchange = Column(Text, nullable=False)
    quantity = Column(Integer, server_default="0")
    buy_quantity = Column(Integer, server_default="0")
    sell_quantity = Column(Integer, server_default="0")
    average_buy_price = Column(Float, server_default="0")
    average_sell_price = Column(Float, server_default="0")
    unrealised_pnl = Column(Float, server_default="0")
    realised_pnl = Column(Float, server_default="0")
    m2m = Column(Float, server_default="0")
    product = Column(Text, nullable=False)
    snapshot_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(UUID, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    action = Column(Text, nullable=False)
    resource = Column(Text, nullable=False)
    resource_id = Column(Text, server_default="")
    details = Column(JSONB, server_default="{}")
    ip_address = Column(Text, server_default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SymbolMaster(Base):
    __tablename__ = "symbol_master"
    __table_args__ = (UniqueConstraint("broker", "token"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    symbol = Column(Text, nullable=False)
    exchange = Column(Text, nullable=False)
    broker = Column(Text, nullable=False)
    broker_symbol = Column(Text, nullable=False)
    token = Column(Text, nullable=False)
    instrument_type = Column(Text, server_default="")
    lot_size = Column(Integer, server_default="1")
    tick_size = Column(Float, server_default="0.05")
    segment = Column(Text, server_default="")
    last_updated = Column(Date, server_default=func.current_date())


class Plan(Base):
    __tablename__ = "plans"

    id = Column(Text, primary_key=True)
    name = Column(Text, nullable=False)
    price_monthly = Column(Integer, server_default="0")
    price_yearly = Column(Integer, server_default="0")
    max_brokers = Column(Integer, server_default="1")
    max_strategies = Column(Integer, server_default="1")
    max_symbols = Column(Integer, server_default="5")
    live_trading = Column(Boolean, server_default="false")
    ai_desk = Column(Boolean, server_default="false")
    api_access = Column(Boolean, server_default="false")
    description = Column(Text, server_default="")
    features = Column(JSONB, server_default="[]")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(UUID, primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(UUID, ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False, index=True)
    razorpay_subscription_id = Column(String(64), nullable=False, unique=True)
    razorpay_plan_id = Column(String(64), nullable=False)
    tier = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, server_default="created")
    current_period_start = Column(DateTime(timezone=True), nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    trial_end = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class UserStrategy(Base):
    __tablename__ = "user_strategies"

    id = Column(UUID, primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(UUID, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    strategy_type = Column(Text, server_default="buyer")
    status = Column(Text, server_default="draft")
    index_symbol = Column(Text, server_default="NIFTY")
    entry_time = Column(Text, nullable=True)
    exit_time = Column(Text, nullable=True)
    days_of_week = Column(ARRAY(Integer), server_default="{1,2,3,4,5}")
    underlying_from = Column(Text, server_default="option_chain")
    underlying_sl_type = Column(Text, nullable=True)
    underlying_sl_value = Column(Float, nullable=True)
    underlying_target_type = Column(Text, nullable=True)
    underlying_target_value = Column(Float, nullable=True)
    overall_sl_type = Column(Text, nullable=True)
    overall_sl_value = Column(Float, nullable=True)
    overall_target_type = Column(Text, nullable=True)
    overall_target_value = Column(Float, nullable=True)
    legs = Column(JSONB, server_default="[]")
    config = Column(JSONB, server_default="{}")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class StrategyHealth(Base):
    __tablename__ = "strategy_health"

    strategy_id = Column(Text, primary_key=True)
    user_id = Column(UUID, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=True)
    status = Column(Text, server_default="draft")
    last_run = Column(DateTime(timezone=True), nullable=True)
    run_count = Column(Integer, server_default="0")
    error_count = Column(Integer, server_default="0")
    last_error = Column(Text, nullable=True)
    heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
