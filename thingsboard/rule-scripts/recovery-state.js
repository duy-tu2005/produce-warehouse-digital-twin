var eventTs = parseInt(metadata.ts, 10);
if (!isFinite(eventTs) || eventTs <= 0) {
    eventTs = Date.now();
}

msg = {
    last_seen: eventTs,
    observed_state: "RECOVERY",
    expected_state: "NORMAL",
    health_score: 60,
    anomaly_score: 0,
    anomaly_type: "NONE",
    anomaly: false,
    severity: "NONE",
    online: true,
    state_match: false,
    recovery_count: 0,
    previous_anomaly_type: "CONNECTION_LOST",
    active_anomalies: "[]",
    anomaly_details: "{\"reason\":\"Device activity resumed\"}"
};

metadata.prevAlarmType = "CONNECTION_LOST";
metadata.alarmType = "NONE";
metadata.alarmSeverity = "INDETERMINATE";

return { msg: msg, metadata: metadata, msgType: "POST_TELEMETRY_REQUEST" };

