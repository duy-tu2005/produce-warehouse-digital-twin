var twin = {
    last_seen: msg.last_seen,
    observed_state: msg.observed_state,
    expected_state: msg.expected_state,
    health_score: msg.health_score,
    anomaly_score: msg.anomaly_score,
    anomaly_type: msg.anomaly_type,
    anomaly: msg.anomaly,
    severity: msg.severity,
    online: msg.online,
    state_match: msg.state_match,
    active_anomalies: msg.active_anomalies,
    anomaly_details: msg.anomaly_details,
    previous_anomaly_type: msg.previous_anomaly_type,
    recovery_count: msg.recovery_count,
    expected_led_state: msg.expected_led_state,
    actuator_mismatch_count: msg.actuator_mismatch_count
};

return { msg: twin, metadata: metadata, msgType: "POST_TELEMETRY_REQUEST" };
