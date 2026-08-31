import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _enum_values(enum_cls):
    return [e.value for e in enum_cls]


class MissionCategory(str, enum.Enum):
    REGULAR = "regular"
    IBADAH = "ibadah"
    ADDITIONAL = "additional"


class MissionDifficulty(str, enum.Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class CompletionStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class RedemptionStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class RedemptionType(str, enum.Enum):
    REWARD = "reward"
    CASH = "cash"


class TransactionType(str, enum.Enum):
    MISSION = "mission"
    ACHIEVEMENT = "achievement"
    PUNISHMENT = "punishment"
    REDEMPTION = "redemption"
    ADJUSTMENT = "adjustment"
    QUIZ = "quiz"


class RecipientRole(str, enum.Enum):
    PARENT = "parent"
    CHILD = "child"


class NotificationType(str, enum.Enum):
    MISSION_PENDING = "mission_pending"
    MISSION_APPROVED = "mission_approved"
    MISSION_REJECTED = "mission_rejected"
    REDEMPTION_PENDING = "redemption_pending"
    REDEMPTION_APPROVED = "redemption_approved"
    REDEMPTION_REJECTED = "redemption_rejected"
    ACHIEVEMENT = "achievement"
    PUNISHMENT = "punishment"
    INACTIVITY = "inactivity"
    AGENDA = "agenda"
    QUIZ = "quiz"
    CHAT = "chat"
    SYSTEM = "system"


class ParentRole(str, enum.Enum):
    FATHER = "father"
    MOTHER = "mother"
    GUARDIAN = "guardian"


class EmailTokenPurpose(str, enum.Enum):
    VERIFY_EMAIL = "verify_email"
    RESET_PASSWORD = "reset_password"


class Family(Base):
    __tablename__ = "families"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    family_name: Mapped[str] = mapped_column(String(100))
    family_code: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    rupiah_per_point: Mapped[int] = mapped_column(Integer, default=1000)
    daily_point_limit: Mapped[int] = mapped_column(Integer, default=50)
    min_cash_redemption: Mapped[int] = mapped_column(Integer, default=100)
    quiz_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    chat_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    agenda_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    rewards_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mission_evidence_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    daily_mission_limit: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    referral_code: Mapped[str | None] = mapped_column(String(8), unique=True, nullable=True, index=True)
    referred_by_family_id: Mapped[int | None] = mapped_column(
        ForeignKey("families.id", ondelete="SET NULL"), nullable=True, index=True
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    activation_preset: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    parents: Mapped[list["Parent"]] = relationship(back_populates="family", cascade="all, delete-orphan")
    children: Mapped[list["Child"]] = relationship(back_populates="family", cascade="all, delete-orphan")
    missions: Mapped[list["Mission"]] = relationship(back_populates="family", cascade="all, delete-orphan")
    punishments: Mapped[list["Punishment"]] = relationship(back_populates="family", cascade="all, delete-orphan")
    rewards: Mapped[list["Reward"]] = relationship(back_populates="family", cascade="all, delete-orphan")
    settings_history: Mapped[list["SettingsHistory"]] = relationship(
        back_populates="family", cascade="all, delete-orphan"
    )
    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="family", cascade="all, delete-orphan"
    )
    agenda_items: Mapped[list["FamilyAgenda"]] = relationship(
        back_populates="family", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        back_populates="family", cascade="all, delete-orphan"
    )


class Parent(Base):
    __tablename__ = "parents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[ParentRole] = mapped_column(
        Enum(ParentRole, values_callable=_enum_values, native_enum=False),
        default=ParentRole.FATHER,
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    terms_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    privacy_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    parental_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    child_data_protection_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    legal_doc_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    family: Mapped["Family"] = relationship(back_populates="parents")
    email_tokens: Mapped[list["EmailToken"]] = relationship(
        back_populates="parent", cascade="all, delete-orphan"
    )


class EmailToken(Base):
    __tablename__ = "email_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_id: Mapped[int] = mapped_column(ForeignKey("parents.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), index=True)
    purpose: Mapped[EmailTokenPurpose] = mapped_column(
        Enum(EmailTokenPurpose, values_callable=_enum_values, native_enum=False)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    parent: Mapped["Parent"] = relationship(back_populates="email_tokens")


class ParentInvite(Base):
    __tablename__ = "parent_invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), index=True)
    invited_by_parent_id: Mapped[int] = mapped_column(ForeignKey("parents.id", ondelete="CASCADE"))
    email: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[ParentRole] = mapped_column(
        Enum(ParentRole, values_callable=_enum_values, native_enum=False)
    )
    token_hash: Mapped[str] = mapped_column(String(64), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReferralInvite(Base):
    __tablename__ = "referral_invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    referrer_family_id: Mapped[int] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), index=True)
    invitee_email: Mapped[str] = mapped_column(String(255), index=True)
    referral_code: Mapped[str] = mapped_column(String(8))
    token_hash: Mapped[str] = mapped_column(String(64), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Child(Base):
    __tablename__ = "children"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    color: Mapped[str] = mapped_column(String(7), default="#6366f1")
    weekly_target: Mapped[int] = mapped_column(Integer, default=100)
    pin_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    lifetime_points: Mapped[int] = mapped_column(Integer, default=0)
    active_balance: Mapped[int] = mapped_column(Integer, default=0)
    total_redeemed: Mapped[int] = mapped_column(Integer, default=0)
    current_streak: Mapped[int] = mapped_column(Integer, default=0)
    longest_streak: Mapped[int] = mapped_column(Integer, default=0)
    last_activity_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    family: Mapped["Family"] = relationship(back_populates="children")
    completions: Mapped[list["MissionCompletion"]] = relationship(
        back_populates="child", cascade="all, delete-orphan"
    )
    achievements: Mapped[list["Achievement"]] = relationship(back_populates="child", cascade="all, delete-orphan")
    punishment_records: Mapped[list["PunishmentRecord"]] = relationship(
        back_populates="child", cascade="all, delete-orphan"
    )
    transactions: Mapped[list["PointTransaction"]] = relationship(
        back_populates="child", cascade="all, delete-orphan"
    )
    redemptions: Mapped[list["RedemptionRequest"]] = relationship(
        back_populates="child", cascade="all, delete-orphan"
    )
    goals: Mapped[list["Goal"]] = relationship(back_populates="child", cascade="all, delete-orphan")
    badges: Mapped[list["ChildBadge"]] = relationship(back_populates="child", cascade="all, delete-orphan")


class Mission(Base):
    __tablename__ = "missions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[MissionCategory] = mapped_column(Enum(MissionCategory))
    points: Mapped[int] = mapped_column(Integer, default=0)
    difficulty: Mapped[MissionDifficulty] = mapped_column(Enum(MissionDifficulty), default=MissionDifficulty.EASY)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    family: Mapped["Family"] = relationship(back_populates="missions")
    completions: Mapped[list["MissionCompletion"]] = relationship(
        back_populates="mission", cascade="all, delete-orphan"
    )


class Punishment(Base):
    __tablename__ = "punishments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    points_deducted: Mapped[int] = mapped_column(Integer, default=5)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    family: Mapped["Family"] = relationship(back_populates="punishments")


class Reward(Base):
    __tablename__ = "rewards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    points_cost: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    family: Mapped["Family"] = relationship(back_populates="rewards")


class MissionCompletion(Base):
    __tablename__ = "mission_completions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    child_id: Mapped[int] = mapped_column(ForeignKey("children.id", ondelete="CASCADE"), index=True)
    mission_id: Mapped[int] = mapped_column(ForeignKey("missions.id", ondelete="CASCADE"), index=True)
    status: Mapped[CompletionStatus] = mapped_column(Enum(CompletionStatus), default=CompletionStatus.PENDING)
    points_awarded: Mapped[int] = mapped_column(Integer, default=0)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    proof_image: Mapped[str | None] = mapped_column(Text, nullable=True)

    child: Mapped["Child"] = relationship(back_populates="completions")
    mission: Mapped["Mission"] = relationship(back_populates="completions")


class Achievement(Base):
    __tablename__ = "achievements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    child_id: Mapped[int] = mapped_column(ForeignKey("children.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    points: Mapped[int] = mapped_column(Integer, default=5)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    child: Mapped["Child"] = relationship(back_populates="achievements")


class PunishmentRecord(Base):
    __tablename__ = "punishment_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    child_id: Mapped[int] = mapped_column(ForeignKey("children.id", ondelete="CASCADE"), index=True)
    punishment_id: Mapped[int | None] = mapped_column(ForeignKey("punishments.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    points_deducted: Mapped[int] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    child: Mapped["Child"] = relationship(back_populates="punishment_records")


class PointTransaction(Base):
    __tablename__ = "point_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    child_id: Mapped[int] = mapped_column(ForeignKey("children.id", ondelete="CASCADE"), index=True)
    transaction_type: Mapped[TransactionType] = mapped_column(Enum(TransactionType))
    points: Mapped[int] = mapped_column(Integer)
    active_balance_after: Mapped[int] = mapped_column(Integer)
    lifetime_points_after: Mapped[int] = mapped_column(Integer)
    rupiah_per_point: Mapped[int] = mapped_column(Integer, default=1000)
    description: Mapped[str] = mapped_column(String(300))
    reference_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    child: Mapped["Child"] = relationship(back_populates="transactions")


class RedemptionRequest(Base):
    __tablename__ = "redemption_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    child_id: Mapped[int] = mapped_column(ForeignKey("children.id", ondelete="CASCADE"), index=True)
    redemption_type: Mapped[RedemptionType] = mapped_column(Enum(RedemptionType))
    reward_id: Mapped[int | None] = mapped_column(ForeignKey("rewards.id", ondelete="SET NULL"), nullable=True)
    points: Mapped[int] = mapped_column(Integer)
    rupiah_per_point: Mapped[int] = mapped_column(Integer)
    status: Mapped[RedemptionStatus] = mapped_column(Enum(RedemptionStatus), default=RedemptionStatus.PENDING)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    child: Mapped["Child"] = relationship(back_populates="redemptions")
    reward: Mapped["Reward | None"] = relationship()


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    child_id: Mapped[int] = mapped_column(ForeignKey("children.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    target_points: Mapped[int] = mapped_column(Integer)
    is_achieved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    child: Mapped["Child"] = relationship(back_populates="goals")


class BadgeDefinition(Base):
    __tablename__ = "badge_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(300))
    icon: Mapped[str] = mapped_column(String(10), default="🏅")
    min_lifetime_points: Mapped[int] = mapped_column(Integer, default=0)


class ChildBadge(Base):
    __tablename__ = "child_badges"
    __table_args__ = (UniqueConstraint("child_id", "badge_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    child_id: Mapped[int] = mapped_column(ForeignKey("children.id", ondelete="CASCADE"), index=True)
    badge_id: Mapped[int] = mapped_column(ForeignKey("badge_definitions.id", ondelete="CASCADE"))
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    child: Mapped["Child"] = relationship(back_populates="badges")
    badge: Mapped["BadgeDefinition"] = relationship()


class SettingsHistory(Base):
    __tablename__ = "settings_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), index=True)
    rupiah_per_point: Mapped[int] = mapped_column(Integer)
    daily_point_limit: Mapped[int] = mapped_column(Integer)
    min_cash_redemption: Mapped[int] = mapped_column(Integer)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)

    family: Mapped["Family"] = relationship(back_populates="settings_history")


class WeeklySalarySnapshot(Base):
    __tablename__ = "weekly_salary_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    child_id: Mapped[int] = mapped_column(ForeignKey("children.id", ondelete="CASCADE"), index=True)
    week_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    week_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    points_earned: Mapped[int] = mapped_column(Integer, default=0)
    points_deducted: Mapped[int] = mapped_column(Integer, default=0)
    net_points: Mapped[int] = mapped_column(Integer, default=0)
    rupiah_per_point: Mapped[int] = mapped_column(Integer)
    salary_rupiah: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), index=True)
    recipient_role: Mapped[RecipientRole] = mapped_column(Enum(RecipientRole), index=True)
    child_id: Mapped[int | None] = mapped_column(ForeignKey("children.id", ondelete="CASCADE"), nullable=True, index=True)
    type: Mapped[NotificationType] = mapped_column(Enum(NotificationType))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(String(500))
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    family: Mapped["Family"] = relationship(back_populates="notifications")


class FamilyAgenda(Base):
    __tablename__ = "family_agenda"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_date: Mapped[date] = mapped_column(Date, index=True)
    event_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    all_day: Mapped[bool] = mapped_column(Boolean, default=True)
    color: Mapped[str] = mapped_column(String(7), default="#3b82f6")
    child_id: Mapped[int | None] = mapped_column(ForeignKey("children.id", ondelete="CASCADE"), nullable=True, index=True)
    reminder_hours_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    family: Mapped["Family"] = relationship(back_populates="agenda_items")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), index=True)
    actor_role: Mapped[str] = mapped_column(String(20), index=True)
    actor_label: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(50), index=True)
    entity_type: Mapped[str] = mapped_column(String(50), index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str] = mapped_column(String(500))
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    family: Mapped["Family"] = relationship(back_populates="audit_logs")


class PlatformAdmin(Base):
    __tablename__ = "platform_admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(100), default="Super Admin")
    notification_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlatformNotification(Base):
    __tablename__ = "platform_notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    family_id: Mapped[int | None] = mapped_column(ForeignKey("families.id", ondelete="SET NULL"), nullable=True, index=True)
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    family: Mapped["Family | None"] = relationship()


class PlatformAuditLog(Base):
    __tablename__ = "platform_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform_admin_id: Mapped[int] = mapped_column(ForeignKey("platform_admins.id", ondelete="CASCADE"), index=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), index=True)
    feature_key: Mapped[str] = mapped_column(String(50), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean)
    summary: Mapped[str] = mapped_column(String(500))
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    platform_admin: Mapped["PlatformAdmin"] = relationship()
    family: Mapped["Family"] = relationship()


class QuizTemplate(Base):
    __tablename__ = "quiz_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject: Mapped[str] = mapped_column(String(100), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sub_material: Mapped[str | None] = mapped_column(String(200), nullable=True)
    grade_level: Mapped[str] = mapped_column(String(50), default="SD")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    questions: Mapped[list["QuizTemplateQuestion"]] = relationship(
        back_populates="template", cascade="all, delete-orphan"
    )


class QuizTemplateQuestion(Base):
    __tablename__ = "quiz_template_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("quiz_templates.id", ondelete="CASCADE"), index=True)
    question: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    options: Mapped[list] = mapped_column(JSON)
    correct_index: Mapped[int] = mapped_column(Integer)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    template: Mapped["QuizTemplate"] = relationship(back_populates="questions")


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), index=True)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("quiz_templates.id", ondelete="SET NULL"), nullable=True)
    subject: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(200))
    sub_material: Mapped[str | None] = mapped_column(String(200), nullable=True)
    points_reward: Mapped[int] = mapped_column(Integer, default=10)
    passing_score: Mapped[int] = mapped_column(Integer, default=70)
    questions_per_attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_all_children: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    questions: Mapped[list["QuizQuestion"]] = relationship(back_populates="quiz", cascade="all, delete-orphan")
    attempts: Mapped[list["QuizAttempt"]] = relationship(back_populates="quiz", cascade="all, delete-orphan")
    child_targets: Mapped[list["QuizChildTarget"]] = relationship(back_populates="quiz", cascade="all, delete-orphan")


class QuizChildTarget(Base):
    __tablename__ = "quiz_child_targets"

    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"), primary_key=True)
    child_id: Mapped[int] = mapped_column(ForeignKey("children.id", ondelete="CASCADE"), primary_key=True)

    quiz: Mapped["Quiz"] = relationship(back_populates="child_targets")


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"), index=True)
    question: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    options: Mapped[list] = mapped_column(JSON)
    correct_index: Mapped[int] = mapped_column(Integer)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    quiz: Mapped["Quiz"] = relationship(back_populates="questions")


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    child_id: Mapped[int] = mapped_column(ForeignKey("children.id", ondelete="CASCADE"), index=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"), index=True)
    score: Mapped[int] = mapped_column(Integer)
    total_questions: Mapped[int] = mapped_column(Integer)
    passed: Mapped[bool] = mapped_column(Boolean)
    points_awarded: Mapped[int] = mapped_column(Integer, default=0)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    child: Mapped["Child"] = relationship()
    quiz: Mapped["Quiz"] = relationship(back_populates="attempts")


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_monthly: Mapped[int] = mapped_column(Integer, default=0)
    price_yearly: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="IDR")
    trial_days: Mapped[int] = mapped_column(Integer, default=14)
    feature_preset: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="plan")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), unique=True, index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="trial", index=True)
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    manual_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    family: Mapped["Family"] = relationship()
    plan: Mapped["Plan"] = relationship(back_populates="subscriptions")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), index=True)
    subscription_id: Mapped[int | None] = mapped_column(ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True)
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="IDR")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    provider: Mapped[str] = mapped_column(String(30), default="manual")
    provider_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payment_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    proof_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("platform_admins.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    family: Mapped["Family"] = relationship()
    subscription: Mapped["Subscription | None"] = relationship()


class PlatformBroadcast(Base):
    __tablename__ = "platform_broadcasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform_admin_id: Mapped[int] = mapped_column(ForeignKey("platform_admins.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    target: Mapped[str] = mapped_column(String(20), default="all_active")
    families_reached: Mapped[int] = mapped_column(Integer, default=0)
    send_email: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    platform_admin: Mapped["PlatformAdmin"] = relationship()


class PlatformPaymentSettings(Base):
    __tablename__ = "platform_payment_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    qris_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    qris_merchant_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bank_account_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bank_account_holder: Mapped[str | None] = mapped_column(String(100), nullable=True)
    transfer_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_methods_enabled: Mapped[dict] = mapped_column(
        JSON,
        default=lambda: {"qris_static": True, "bank_transfer": True},
        server_default='{"qris_static": true, "bank_transfer": true}',
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), index=True)
    child_id: Mapped[int] = mapped_column(ForeignKey("children.id", ondelete="CASCADE"), index=True)
    sender_role: Mapped[str] = mapped_column(String(20))
    body: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
