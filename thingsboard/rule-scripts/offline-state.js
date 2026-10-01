var eventTs = parseInt(metadata.ts, 10);
if (!isFinite(eventTs) || eventTs <= 0) {
    eventTs = Date.now();
}

var previousAnomalyType = "NONE";
if (metadata.anomaly_type !== null && metadata.anomaly_type !== undefined) {
    try {
        var previous = typeof metadata.anomaly_type === "string" ?
            JSON.parse(metadata.anomaly_type) : metadata.anomaly_type;
        previousAnomalyType = previous && previous.value !== undefined ?
            String(previous.value) : String(previous);
    } catch (ignore) {
        previousAnomalyType = String(metadata.anomaly_type);
    }
}

msg = {
    last_seen: eventTs,
    observed_state: "OFFLINE",
    expected_state: "NORMAL",
    health_score: 0,
    anomaly_score: 100,
    anomaly_type: "CONNECTION_LOST",
    anomaly: true,
    severity: "CRITICAL",
    online: false,
    state_match: false,
    recovery_count: 0,
    previous_anomaly_type: previousAnomalyType,
    active_anomalies: "[\"CONNECTION_LOST\"]",
    anomaly_details: "{\"reason\":\"No device activity before inactivity timeout\"}"
};

metadata.prevAlarmType = previousAnomalyType;
metadata.alarmType = "CONNECTION_LOST";
metadata.alarmSeverity = "CRITICAL";

return { msg: msg, metadata: metadata, msgType: "POST_TELEMETRY_REQUEST" };
