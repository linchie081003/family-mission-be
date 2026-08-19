from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.services.proof_image import normalize_image_data_url


# Auth
class FamilyRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    family_name: str = Field(min_length=2, max_length=100)


class FamilyLogin(BaseModel):
    email: EmailStr
    password: str


class ChildLoginSelect(BaseModel):
    family_code: str
    child_id: int
    pin: str


class ChildSetPin(BaseModel):
    pin: str = Field(min_length=4, max_length=6, pattern=r"^\d+$")


class ChildPinChange(BaseModel):
    current_pin: str = Field(min_length=4, max_length=6, pattern=r"^\d+$")
    pin: str = Field(min_length=4, max_length=6, pattern=r"^\d+$")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    family_id: Optional[int] = None
    child_id: Optional[int] = None


class RegisterResponse(BaseModel):
    status: str
    message: str
    family_id: int


class FamilyPublic(BaseModel):
    id: int
    email: str
    family_name: str
    family_code: str
    rupiah_per_point: int
    daily_point_limit: int
    min_cash_redemption: int
    quiz_enabled: bool = False
    chat_enabled: bool = False
    agenda_enabled: bool = False
    is_active: bool = True

    model_config = {"from_attributes": True}


class ParentPasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6)


class PlatformAdminLogin(BaseModel):
    email: str = Field(min_length=3)
    password: str


class PlatformAdminPublic(BaseModel):
    id: int
    email: str
    name: str
    notification_email: Optional[str] = None

    model_config = {"from_attributes": True}


class PlatformAdminProfileUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    notification_email: Optional[EmailStr] = None


class PlatformNotificationPublic(BaseModel):
    id: int
    type: str
    title: str
    body: str
    family_id: Optional[int] = None
    data: Optional[dict] = None
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PlatformFamilyPublic(BaseModel):
    id: int
    email: str
    family_name: str
    family_code: str
    quiz_enabled: bool
    chat_enabled: bool
    agenda_enabled: bool
    is_active: bool
    children_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class PlatformFamilyFeaturesUpdate(BaseModel):
    quiz_enabled: Optional[bool] = None
    chat_enabled: Optional[bool] = None
    agenda_enabled: Optional[bool] = None
    is_active: Optional[bool] = None


class PlatformAuditLogPublic(BaseModel):
    id: int
    platform_admin_id: int
    family_id: int
    feature_key: str
    enabled: bool
    summary: str
    details: Optional[dict] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# Child
class ChildCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    color: str = "#6366f1"
    weekly_target: int = 100


class ChildUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    weekly_target: Optional[int] = None


class ChildPublic(BaseModel):
    id: int
    name: str
    color: str
    weekly_target: int
    avatar_url: Optional[str] = None
    lifetime_points: int
    active_balance: int
    spendable_balance: int
    reward_redeemed_total: int
    total_redeemed: int
    current_streak: int
    longest_streak: int
    level: str
    has_pin: bool

    model_config = {"from_attributes": True}


class ChildListItem(BaseModel):
    id: int
    name: str
    color: str
    has_pin: bool

    model_config = {"from_attributes": True}


# Mission
class MissionCreate(BaseModel):
    title: str
    description: Optional[str] = None
    category: str
    points: int = 0
    difficulty: str = "easy"


class MissionUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    points: Optional[int] = None
    difficulty: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class MissionPublic(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    category: str
    points: int
    difficulty: str
    is_active: bool
    sort_order: int
    completed_today: bool = False
    pending_approval: bool = False

    model_config = {"from_attributes": True}


# Punishment & Reward
class PunishmentCreate(BaseModel):
    title: str
    points_deducted: int = 5


class PunishmentPublic(BaseModel):
    id: int
    title: str
    points_deducted: int
    is_active: bool

    model_config = {"from_attributes": True}


class RewardCreate(BaseModel):
    title: str
    description: Optional[str] = None
    points_cost: int


class RewardPublic(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    points_cost: int
    is_active: bool

    model_config = {"from_attributes": True}


# Actions
class AchievementCreate(BaseModel):
    title: str
    points: int = 5
    note: Optional[str] = None


class PunishmentRecordCreate(BaseModel):
    punishment_id: Optional[int] = None
    title: str
    points_deducted: int
    note: Optional[str] = None


class MissionCompleteRequest(BaseModel):
    mission_id: int
    note: Optional[str] = None
    proof_image: str = Field(min_length=50)


class ParentMissionRecordRequest(BaseModel):
    mission_id: int
    completed_date: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    note: Optional[str] = None
    proof_image: Optional[str] = None


class RedemptionCreate(BaseModel):
    redemption_type: str
    reward_id: Optional[int] = None
    points: int
    note: Optional[str] = None


class GoalCreate(BaseModel):
    title: str
    target_points: int


class GoalPublic(BaseModel):
    id: int
    title: str
    target_points: int
    is_achieved: bool

    model_config = {"from_attributes": True}


# Settings
class SettingsUpdate(BaseModel):
    rupiah_per_point: Optional[int] = None
    daily_point_limit: Optional[int] = None
    min_cash_redemption: Optional[int] = None
    note: Optional[str] = None


class SettingsHistoryPublic(BaseModel):
    id: int
    rupiah_per_point: int
    daily_point_limit: int
    min_cash_redemption: int
    changed_at: datetime
    note: Optional[str] = None

    model_config = {"from_attributes": True}


# Dashboard & Reports
class ChildRanking(BaseModel):
    id: int
    name: str
    color: str
    lifetime_points: int
    active_balance: int
    weekly_points: int
    level: str
    rank: int


class DashboardSummary(BaseModel):
    total_weekly_points: int
    total_lifetime_points: int
    total_active_balance: int
    pending_count: int
    children_ranking: list[ChildRanking]


class PendingItem(BaseModel):
    id: int
    type: str
    child_name: str
    child_color: str
    title: str
    points: int
    created_at: datetime
    extra: Optional[dict] = None


class TransactionPublic(BaseModel):
    id: int
    transaction_type: str
    points: int
    active_balance_after: int
    lifetime_points_after: int
    description: str
    created_at: datetime

    model_config = {"from_attributes": True}


class WeeklyPointsReport(BaseModel):
    week_start: datetime
    week_end: datetime
    points_earned: int
    points_deducted: int
    net_points: int


class BadgePublic(BaseModel):
    id: int
    code: str
    name: str
    description: str
    icon: str
    earned_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ChildReportSummary(BaseModel):
    id: int
    name: str
    color: str
    weekly_points: int
    lifetime_points: int
    spendable_balance: int
    reward_redeemed_total: int
    recent_transactions: list[TransactionPublic]
    weekly_evaluations: list[WeeklyPointsReport]


class ChildDetailSummary(BaseModel):
    child: ChildPublic
    weekly_points: int
    weekly_evaluations: list[WeeklyPointsReport]
    badges: list[BadgePublic]
    recent_transactions: list[TransactionPublic]


class RedemptionSummary(BaseModel):
    total_redeemed: int
    total_reward_points: int = 0
    total_cash_points: int = 0
    redemptions: list[dict]


class PointsSummary(BaseModel):
    child_id: Optional[int] = None
    child_name: Optional[str] = None
    child_color: Optional[str] = None
    active_balance: int
    lifetime_points: int
    total_redeemed: int
    reward_redeemed_total: int
    cash_redeemed_total: int = 0
    weekly_net_points: int
    weekly_earned: int
    weekly_deducted: int


class FamilyPointsSummary(BaseModel):
    total_lifetime_points: int
    total_active_balance: int
    total_redeemed: int
    total_weekly_net: int
    children: list[PointsSummary]


class AuditLogPublic(BaseModel):
    id: int
    actor_role: str
    actor_label: str
    action: str
    entity_type: str
    entity_id: Optional[int] = None
    summary: str
    details: Optional[dict] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChildHomeData(BaseModel):
    child: ChildPublic
    today_missions: list[MissionPublic]
    weekly_progress: float
    active_goal: Optional[GoalPublic] = None
    recent_badges: list[BadgePublic]
    quiz_enabled: bool = False
    chat_enabled: bool = False
    chat_unread_count: int = 0


# Notifications
class NotificationPublic(BaseModel):
    id: int
    type: str
    title: str
    body: str
    data: Optional[dict] = None
    is_read: bool
    child_id: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class UnreadCountResponse(BaseModel):
    count: int


# Agenda
class AgendaCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    event_date: str
    event_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    all_day: bool = True
    color: str = "#3b82f6"
    child_id: Optional[int] = None
    reminder_hours_before: Optional[int] = Field(None, ge=1, le=168)


class AgendaUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    event_date: Optional[str] = None
    event_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    all_day: Optional[bool] = None
    color: Optional[str] = None
    child_id: Optional[int] = None
    reminder_hours_before: Optional[int] = Field(None, ge=1, le=168)


class AgendaPublic(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    event_date: str
    event_time: Optional[str] = None
    all_day: bool
    color: str
    child_id: Optional[int] = None
    reminder_hours_before: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CalendarDayMission(BaseModel):
    id: int
    title: str
    status: str
    points: int


class CalendarDayAgenda(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    time: Optional[str] = None
    all_day: bool
    color: str
    child_id: Optional[int] = None


class CalendarDayData(BaseModel):
    missions: list[CalendarDayMission]
    agenda: list[CalendarDayAgenda]
    net_points: int


class CalendarResponse(BaseModel):
    month: str
    child_id: int
    days: dict[str, CalendarDayData]


class FamilyOverviewChildDay(BaseModel):
    child_id: int
    child_name: str
    child_color: str
    missions: list[CalendarDayMission]
    agenda: list[CalendarDayAgenda]
    net_points: int


class FamilyOverviewDay(BaseModel):
    family_agenda: list[CalendarDayAgenda]
    children: list[FamilyOverviewChildDay]


class FamilyOverviewCalendarResponse(BaseModel):
    month: str
    days: dict[str, FamilyOverviewDay]


class QuizSubmitRequest(BaseModel):
    answers: list["QuizAnswerSubmit"] = Field(min_length=1)


class QuizAnswerSubmit(BaseModel):
    question_id: int
    selected_option: str = Field(min_length=1, max_length=500)


class QuizQuestionInput(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    image_url: Optional[str] = None
    options: list[str] = Field(min_length=2, max_length=6)
    correct_index: int = Field(ge=0)
    explanation: Optional[str] = None

    @field_validator("image_url")
    @classmethod
    def validate_image_url(cls, value: Optional[str]) -> Optional[str]:
        return normalize_image_data_url(value, required=False)

    @field_validator("options")
    @classmethod
    def validate_options(cls, value: list[str]) -> list[str]:
        cleaned = [o.strip() for o in value if o and o.strip()]
        if len(cleaned) < 2:
            raise ValueError("Minimal 2 pilihan jawaban valid")
        return cleaned

    @field_validator("correct_index")
    @classmethod
    def validate_correct_index(cls, value: int, info) -> int:
        options = info.data.get("options") or []
        if options and value >= len(options):
            raise ValueError("correct_index di luar range options")
        return value


class QuizQuestionPublic(BaseModel):
    id: Optional[int] = None
    question: str
    image_url: Optional[str] = None
    options: list[str]
    correct_index: int
    explanation: Optional[str] = None
    sort_order: int = 0


class QuizTemplateCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    sub_material: Optional[str] = Field(default=None, max_length=200)
    grade_level: str = Field(default="SD", max_length=50)
    questions: list[QuizQuestionInput] = Field(min_length=1)


class QuizTemplateUpdate(BaseModel):
    subject: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    sub_material: Optional[str] = Field(default=None, max_length=200)
    grade_level: str = Field(default="SD", max_length=50)
    questions: list[QuizQuestionInput] = Field(min_length=1)


class QuizTemplateDetailPublic(BaseModel):
    id: int
    subject: str
    title: str
    description: Optional[str] = None
    sub_material: Optional[str] = None
    grade_level: str
    is_active: bool
    questions: list[QuizQuestionPublic]


class FamilyQuizCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    sub_material: Optional[str] = Field(default=None, max_length=200)
    points_reward: int = Field(default=10, ge=1)
    passing_score: int = Field(default=70, ge=50, le=100)
    questions_per_attempt: Optional[int] = Field(default=None, ge=1)
    target_all_children: bool = True
    assigned_child_ids: list[int] = Field(default_factory=list)
    questions: list[QuizQuestionInput] = Field(min_length=1)


class FamilyQuizUpdate(BaseModel):
    subject: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    sub_material: Optional[str] = Field(default=None, max_length=200)
    points_reward: int = Field(default=10, ge=1)
    passing_score: int = Field(default=70, ge=50, le=100)
    questions_per_attempt: Optional[int] = Field(default=None, ge=1)
    target_all_children: bool = True
    assigned_child_ids: list[int] = Field(default_factory=list)
    questions: list[QuizQuestionInput] = Field(min_length=1)


class FamilyQuizDetailPublic(BaseModel):
    id: int
    subject: str
    title: str
    sub_material: Optional[str] = None
    points_reward: int
    passing_score: int
    questions_per_attempt: Optional[int] = None
    target_all_children: bool = True
    assigned_child_ids: list[int] = Field(default_factory=list)
    is_active: bool
    template_id: Optional[int] = None
    questions: list[QuizQuestionPublic]


class ChatSendRequest(BaseModel):
    body: str = Field(min_length=1, max_length=1000)
