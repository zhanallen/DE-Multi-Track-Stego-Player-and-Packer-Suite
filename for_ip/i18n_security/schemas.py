from pydantic import BaseModel, Field
from typing import Optional

class ClientInfo(BaseModel):
    ip: str = Field(description="The validated real client IP address after anti-spoofing checks.")
    is_proxy_detected: bool = Field(description="Indicates whether a trusted proxy was detected in the request chain.")
    proxy_type: Optional[str] = Field(None, description="The type of proxy detected: 'Cloudflare', 'Generic', or None.")

class I18nInfo(BaseModel):
    detected_locale: str = Field(description="The determined locale for the request.")
    decision_source: str = Field(description="The source of the locale decision (e.g., 'EXPLICIT_COOKIE', 'ACCEPT_LANGUAGE_HEADER', 'CF_EDGE_GEOIP', 'LOCAL_DB_GEOIP', 'SYSTEM_DEFAULT').")
    confidence_score: float = Field(description="A confidence score of the decision between 0.0 and 1.0.")

class GeoInfo(BaseModel):
    country_code: Optional[str] = Field(None, description="The ISO 2-letter country code of the client IP.")
    timezone: Optional[str] = Field(None, description="The timezone of the client IP.")

class ClientContext(BaseModel):
    client: ClientInfo = Field(description="Information about the client IP and proxy details.")
    i18n: I18nInfo = Field(description="Determined language and locale configuration.")
    geo: GeoInfo = Field(description="Location and timezone information.")
