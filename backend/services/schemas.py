from pydantic import BaseModel, Field
from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime


class PromptCreate(BaseModel):
    """Schema for creating a new prompt"""
    prompt_text: str = Field(..., description="The text of the prompt")
    category: str = Field(default="normal", description="Category: normal, suspicious, breaking_in")
    is_suspicious: bool = Field(default=False, description="Whether this prompt indicates suspicious behavior")
    display_order: int = Field(default=0, description="Order for displaying/processing")


class PromptResponse(BaseModel):
    """Schema for prompt response"""
    id: int
    prompt_text: str
    category: Optional[str] = None
    is_suspicious: bool
    display_order: Optional[int] = None


class VerdictResponse(BaseModel):
    """Schema for verdict information"""
    total_analyzed: int = Field(..., description="Total frames analyzed")
    suspicious_frames: int = Field(..., description="Number of suspicious frames")
    normal_frames: int = Field(..., description="Number of normal frames")
    suspicious_percentage: float = Field(..., description="Percentage of suspicious frames")
    risk_level: str = Field(..., description="Risk level assessment")
    risk_color: str = Field(..., description="Color code for risk level")
    needs_attention: bool = Field(..., description="Whether this video needs attention")
    recommendation: str = Field(..., description="Recommendation for action")
    top_suspicious_activities: List[Tuple[str, int]] = Field(
        default_factory=list,
        description="List of top suspicious activities and their counts"
    )
    duration: float = Field(..., description="Video duration in seconds")
    # Multi-threat incident counters
    weapons_count: int = Field(default=0, description="Weapon incidents detected")
    fires_count: int = Field(default=0, description="Fire/smoke incidents detected")
    dogs_count: int = Field(default=0, description="Dog attack incidents detected")
    fights_count: int = Field(default=0, description="Physical violence incidents detected")


class VideoAnalysisRequest(BaseModel):
    """Schema for video analysis request"""
    suspicious_threshold: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Confidence threshold for suspicious behavior"
    )
    log_detections: bool = Field(
        default=False,
        description="Whether to log detections to database"
    )
    buffer_duration: float = Field(
        default=3.0,
        ge=1.0,
        le=10.0,
        description="Duration in seconds for video buffer"
    )
    inference_frequency: float = Field(
        default=1.5,
        ge=0.5,
        le=5.0,
        description="How often to run inference in seconds"
    )
    send_email: bool = Field(
        default=False,
        description="Send email alert if suspicious activity detected"
    )
    email_threshold: float = Field(
        default=15.0,
        ge=0.0,
        le=100.0,
        description="Minimum suspicious percentage to trigger email"
    )


class VideoAnalysisResponse(BaseModel):
    """Schema for video analysis response"""
    video_id: str = Field(..., description="Unique identifier for the video")
    status: str = Field(..., description="Processing status")
    output_video_url: str = Field(..., description="URL to download analyzed video")
    verdict: VerdictResponse = Field(..., description="Analysis verdict")
    processed_at: str = Field(..., description="ISO timestamp of processing completion")


class DetectionResponse(BaseModel):
    """Schema for detection log response"""
    id: int
    video_path: str
    frame_number: int
    detected_action: str
    confidence: float
    is_alert: bool
    timestamp: str


class StatusResponse(BaseModel):
    """Schema for processing status response"""
    task_id: str
    video_id: str
    status: str
    started_at: str
    completed_at: Optional[str] = None
    output_video_url: Optional[str] = None
    verdict: Optional[VerdictResponse] = None
    error: Optional[str] = None


class CCTVIPCreate(BaseModel):
    """Schema for adding a new CCTV IP address"""
    ip_address: str = Field(..., description="The IP address of the CCTV camera")
    location: str = Field(..., description="The location where the camera is installed")
    user_id: int = Field(default=1, description="The user reference")


class CCTVIPResponse(BaseModel):
    """Schema for CCTV IP response"""
    id: int
    ip_address: str
    location: str
    user_id: int
    status: str
    last_checked: datetime
    created_at: datetime


# =====================================================================
# ZERO-PROMPT SURVEILLANCE & VLM EVIDENCE AUDIT SCHEMAS
# =====================================================================

class CameraProfileSchema(BaseModel):
    """Schema for configuring active threat detection modules on a camera"""
    camera_id: str = Field(..., description="Unique camera identifier / name")
    enable_weapon: bool = Field(default=True, description="Scan for guns, knives, weapons")
    enable_fire: bool = True
    enable_dog: bool = True
    enable_fight: bool = True
    enable_coffmap: bool = False
    weapon_conf_threshold: float = Field(default=0.20, ge=0.05, le=0.95)
    fire_conf_threshold: float = Field(default=0.20, ge=0.05, le=0.95)
    dog_conf_threshold: float = Field(default=0.20, ge=0.05, le=0.95)
    fight_conf_threshold: float = Field(default=0.30, ge=0.05, le=0.95)
    save_alert_snapshots: bool = True
    alert_cooldown_seconds: float = Field(default=5.0, ge=1.0, le=60.0)


class ThreatItemSchema(BaseModel):
    type: str = Field(..., description="WEAPON | FIRE_SMOKE | DOG_ATTACK | FIGHT_ASSAULT")
    label: str = Field(..., description="Specific detected label")
    confidence: float
    severity: str = Field(..., description="LOW | MEDIUM | HIGH | CRITICAL")
    bbox: Optional[Dict[str, float]] = None
    is_aggressive: Optional[bool] = None
    track_id: Optional[int] = None


class ContinuousThreatResponse(BaseModel):
    """Real-time zero-prompt frame scan result"""
    camera_id: str
    timestamp: str
    has_threat: bool
    overall_severity: str
    should_trigger_alert: bool
    threats_count: int
    threats: List[ThreatItemSchema]
    latency_ms: float
    annotated_image_base64: Optional[str] = None


class VLMAuditRequest(BaseModel):
    """Schema for operator on-demand evidence verification / forensic search"""
    prompt: str = Field(
        default="Describe what is happening in this incident and verify if there is an actual physical threat.",
        description="Forensic recheck question or natural language query"
    )
    context_type: str = Field(default="security_audit", description="security_audit | space_behavior | general")


class VLMAuditResponse(BaseModel):
    """Schema for VLM multi-modal audit reasoning result"""
    success: bool
    prompt: str
    reasoning: str
    verified_threat: bool
    confidence: float
    model_used: str
    timestamp: str


class CoffMapSpaceRequest(BaseModel):
    sample_stride: int = Field(default=2, ge=1, le=10)
    generate_heatmap: bool = True


class VideoSummaryResponse(BaseModel):
    """Schema for VLM multi-frame video narrative summary"""
    success: bool
    environment: str = "Surveillance Zone"
    narrative_summary: str
    key_events: List[str] = Field(default_factory=list)
    incident_status: str = "ROUTINE_NORMAL"
    confidence: float = 0.85
    latency_seconds: float = 0.0
